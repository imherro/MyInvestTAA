from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_taa.model import asset_file_name
from data.models import PriceBar
from data_provider.tushare_provider import TushareProvider


DEFAULT_START_DATE = "2011-01-01"
BACKGROUND_BENCHMARK_ID = "510500.SH"
DATA_DIRECTORIES = ("research_prices", "execution_prices", "market")


class MarketDataSource(Protocol):
    def get_research_history(
        self, asset_id: str, start: str, end: str
    ) -> list[PriceBar]: ...

    def get_execution_history(
        self, asset_id: str, start: str, end: str
    ) -> list[PriceBar]: ...

    def get_trade_dates(self, start: str, end: str) -> list[str]: ...


class TushareMarketDataSource:
    def __init__(self, token: str | None = None) -> None:
        resolved_token = token or os.getenv("TUSHARE_TOKEN")
        if not resolved_token:
            raise RuntimeError("TUSHARE_TOKEN is required")
        self.token = resolved_token
        self.index_provider = TushareProvider(token=resolved_token, return_type="price")
        self.etf_provider = TushareProvider(token=resolved_token, return_type="qfq")

    def get_research_history(
        self, asset_id: str, start: str, end: str
    ) -> list[PriceBar]:
        # These configured codes are total-return indexes; their raw index levels
        # already include distributions and must not receive ETF adjustment factors.
        return self.index_provider.get_index_history(asset_id, start, end)

    def get_execution_history(
        self, asset_id: str, start: str, end: str
    ) -> list[PriceBar]:
        return self.etf_provider.get_price_history(asset_id, start, end)

    def get_trade_dates(self, start: str, end: str) -> list[str]:
        frame = self.index_provider._client().trade_cal(
            exchange="SSE",
            is_open="1",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
        )
        rows = frame.to_dict("records") if hasattr(frame, "to_dict") else []
        return sorted(
            {
                str(row["cal_date"])
                for row in rows
                if row.get("cal_date") and str(row.get("is_open", "1")) == "1"
            }
        )


def update_market_data(
    *,
    root: Path = ROOT,
    start: str = DEFAULT_START_DATE,
    end: str | None = None,
    source: MarketDataSource | None = None,
    current_runner: Callable[[], None] | None = None,
) -> dict:
    project_root = Path(root)
    resolved_end = end or date.today().isoformat()
    _validate_date_range(start, resolved_end)
    _load_env_file(project_root / ".env")
    market_source = source or TushareMarketDataSource()
    runner = current_runner or (lambda: _run_current_pipeline(project_root))

    assets, mappings, execution_ids = _load_enabled_configuration(project_root)
    stage = Path(tempfile.mkdtemp(prefix="market-stage-", dir=project_root / "data"))
    report_backup = Path(tempfile.mkdtemp(prefix="current-backup-", dir=project_root / "reports"))
    raw_backups: dict[Path, Path] = {}
    try:
        manifest = _build_staged_data(
            stage=stage,
            source=market_source,
            assets=assets,
            mappings=mappings,
            execution_ids=execution_ids,
            start=start,
            end=resolved_end,
        )
        _backup_reports(project_root / "reports" / "current", report_backup)
        raw_backups = _publish_staged_data(project_root / "data", stage)
        try:
            runner()
        except Exception:
            _restore_published_data(raw_backups)
            _restore_reports(project_root / "reports" / "current", report_backup)
            raise
        _discard_backups(raw_backups)
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if report_backup.exists():
            shutil.rmtree(report_backup)


def _load_enabled_configuration(root: Path) -> tuple[list[dict], list[dict], list[str]]:
    assets = _load_json(root / "config" / "research_assets.json")
    mappings = _load_json(root / "config" / "etf_mappings.json")
    enabled_assets = [row for row in assets if row.get("enabled") is True]
    enabled_mappings = [row for row in mappings if row.get("enabled") is True]
    if not enabled_assets or not enabled_mappings:
        raise ValueError("enabled research assets and ETF mappings are required")
    asset_ids = [str(row["asset_id"]) for row in enabled_assets]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("enabled research asset IDs must be unique")
    mapped_ids = [str(row["research_asset_id"]) for row in enabled_mappings]
    if sorted(mapped_ids) != sorted(asset_ids):
        raise ValueError("each enabled research asset must have exactly one enabled ETF mapping")
    if any(row.get("data_source") != "tushare" for row in enabled_assets):
        raise ValueError("all enabled research assets must use Tushare")
    execution_ids = sorted(
        {str(row["etf_id"]) for row in enabled_mappings} | {BACKGROUND_BENCHMARK_ID}
    )
    return enabled_assets, enabled_mappings, execution_ids


def _build_staged_data(
    *,
    stage: Path,
    source: MarketDataSource,
    assets: list[dict],
    mappings: list[dict],
    execution_ids: list[str],
    start: str,
    end: str,
) -> dict:
    research_dir = stage / "research_prices"
    execution_dir = stage / "execution_prices"
    market_dir = stage / "market"
    research_dir.mkdir(parents=True)
    execution_dir.mkdir()
    market_dir.mkdir()

    for asset in assets:
        asset_id = str(asset["asset_id"])
        rows = _price_rows(
            source.get_research_history(asset_id, start, end),
            asset_id=asset_id,
            return_basis="total_return",
            start=start,
            end=end,
        )
        _write_json(research_dir / asset_file_name(asset_id), rows)

    execution_row_count = 0
    for etf_id in execution_ids:
        rows = _price_rows(
            source.get_execution_history(etf_id, start, end),
            asset_id=etf_id,
            return_basis="qfq",
            start=start,
            end=end,
        )
        execution_row_count += len(rows)
        _write_json(execution_dir / asset_file_name(etf_id), rows)

    trade_dates = _validate_trade_dates(source.get_trade_dates(start, end), start, end)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    calendar = {
        "schema_version": "1.0",
        "exchange": "SSE",
        "source": "tushare.trade_cal",
        "source_query": {
            "exchange": "SSE",
            "is_open": "1",
            "start_date": start.replace("-", ""),
            "end_date": end.replace("-", ""),
        },
        "generated_at": generated_at,
        "verified": True,
        "dates": trade_dates,
    }
    _write_json(market_dir / "cn_equity_trade_calendar.json", calendar)

    manifest = {
        "data_provider": "tushare",
        "return_basis": "qfq",
        "generated_at": generated_at,
        "start": start,
        "end": end,
        "mapping_count": len(mappings),
        "unique_asset_count": len(execution_ids),
        "asset_count": len(execution_ids),
        "available_assets": len(execution_ids),
        "row_count": execution_row_count,
        "errors": {},
        "warning": (
            "ETF cache uses actual ETF trading dates only; no index/ETF history "
            "stitching or pre-inception filling."
        ),
    }
    _write_json(execution_dir / "manifest.json", manifest)
    return manifest


def _price_rows(
    bars: list[PriceBar],
    *,
    asset_id: str,
    return_basis: str,
    start: str,
    end: str,
) -> list[dict]:
    rows = sorted(bars, key=lambda bar: bar.date)
    dates = [bar.date for bar in rows]
    if not rows:
        raise ValueError(f"{asset_id} returned no price history")
    if dates != sorted(set(dates)):
        raise ValueError(f"{asset_id} returned duplicate price dates")
    if dates[0] < start or dates[-1] > end:
        raise ValueError(f"{asset_id} returned prices outside the requested range")
    if any(bar.asset_id != asset_id or float(bar.close) <= 0 for bar in rows):
        raise ValueError(f"{asset_id} returned invalid prices")
    return [
        {"date": bar.date, "close": float(bar.close), "return_basis": return_basis}
        for bar in rows
    ]


def _validate_trade_dates(values: list[str], start: str, end: str) -> list[str]:
    dates = sorted(set(str(value) for value in values))
    compact_start = start.replace("-", "")
    compact_end = end.replace("-", "")
    if not dates or any(len(value) != 8 or not value.isdigit() for value in dates):
        raise ValueError("Tushare returned an invalid SSE trade calendar")
    if dates[0] < compact_start or dates[-1] > compact_end:
        raise ValueError("SSE trade calendar contains dates outside the requested range")
    return dates


def _publish_staged_data(data_root: Path, stage: Path) -> dict[Path, Path]:
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    try:
        for name in DATA_DIRECTORIES:
            target = data_root / name
            backup = data_root / f".{name}.previous-market-update"
            if backup.exists():
                shutil.rmtree(backup)
            if target.exists():
                target.replace(backup)
                backups[target] = backup
            (stage / name).replace(target)
            published.append(target)
        return backups
    except Exception:
        for target in reversed(published):
            if target.exists():
                shutil.rmtree(target)
            backup = backups.get(target)
            if backup and backup.exists():
                backup.replace(target)
        for target, backup in backups.items():
            if backup.exists() and not target.exists():
                backup.replace(target)
        raise


def _restore_published_data(backups: dict[Path, Path]) -> None:
    for target, backup in backups.items():
        if target.exists():
            shutil.rmtree(target)
        if backup.exists():
            backup.replace(target)


def _discard_backups(backups: dict[Path, Path]) -> None:
    for backup in backups.values():
        if backup.exists():
            shutil.rmtree(backup)


def _backup_reports(current_dir: Path, backup_dir: Path) -> None:
    if current_dir.exists():
        shutil.copytree(current_dir, backup_dir / "current")


def _restore_reports(current_dir: Path, backup_dir: Path) -> None:
    if current_dir.exists():
        shutil.rmtree(current_dir)
    saved = backup_dir / "current"
    if saved.exists():
        shutil.copytree(saved, current_dir)


def _run_current_pipeline(root: Path) -> None:
    subprocess.run(
        [sys.executable, str(root / "scripts" / "update_current.py")],
        cwd=root,
        check=True,
    )


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _validate_date_range(start: str, end: str) -> None:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date > end_date:
        raise ValueError("start date must not be after end date")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh all CURRENT_TAA market data and rebuild current reports"
    )
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument("--end")
    args = parser.parse_args()
    try:
        manifest = update_market_data(start=args.start, end=args.end)
    except Exception as exc:
        print(f"CURRENT_TAA market update failed: {exc}", file=sys.stderr)
        return 1
    print(
        "CURRENT_TAA market data updated: "
        f"mappings={manifest['mapping_count']} "
        f"unique_etfs={manifest['unique_asset_count']} "
        f"rows={manifest['row_count']} end={manifest['end']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
