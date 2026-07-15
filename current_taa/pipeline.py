from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from current_taa.allocation import build_current_allocation
from current_taa.model import (
    IMPLEMENTATION_VERSION,
    MODEL_DESCRIPTION,
    MODEL_NAME,
    asset_file_name,
    load_json,
    load_price_series,
    load_trade_dates,
    run_research,
)
from current_taa.shadow import BACKGROUND_BENCHMARK_ID, build_shadow


ROOT = Path(__file__).resolve().parents[1]
REPORT_NAMES = {
    "research.json",
    "allocation.json",
    "shadow.json",
    "data_status.json",
    "manifest.json",
}


def run_current_pipeline(
    *,
    root: Path | None = None,
    shadow_start_date: str | None = None,
    output_dir: Path | None = None,
) -> dict:
    project_root = Path(root or ROOT)
    target = Path(output_dir or project_root / "reports" / "current")
    resolved_start = _resolve_shadow_start_date(target, shadow_start_date)
    try:
        reports = _build_reports(project_root, resolved_start)
        _publish_report_set(target, reports)
        return reports
    except Exception as exc:
        failure = {
            "status": "failed",
            "current": False,
            "shadow_start_date": resolved_start,
            "errors": [str(exc)],
        }
        _publish_failure(target, failure)
        raise


def _build_reports(root: Path, shadow_start_date: str) -> dict[str, dict]:
    assets = load_json(root / "config" / "research_assets.json")
    mappings = load_json(root / "config" / "etf_mappings.json")
    trade_dates = load_trade_dates(root / "data" / "market" / "cn_equity_trade_calendar.json")
    research_prices = {}
    index_coverage = []
    for asset in assets:
        if asset.get("enabled") is not True:
            continue
        rows = load_price_series(
            root / "data" / "research_prices" / asset_file_name(asset["asset_id"]),
            "total_return",
        )
        research_prices[asset["asset_id"]] = rows
        index_coverage.append(
            {
                "asset_id": asset["asset_id"],
                "name": asset["name"],
                "first_date": rows[0]["date"],
                "last_date": rows[-1]["date"],
                "row_count": len(rows),
            }
        )
    research_data_end = max(rows[-1]["date"] for rows in research_prices.values())
    trade_dates = [date for date in trade_dates if date <= research_data_end]

    required_etfs = {
        mapping["etf_id"] for mapping in mappings if mapping.get("enabled") is True
    } | {BACKGROUND_BENCHMARK_ID}
    etf_prices = {}
    etf_coverage = []
    mapping_name = {row["etf_id"]: row["etf_name"] for row in mappings}
    mapping_name[BACKGROUND_BENCHMARK_ID] = mapping_name.get(
        BACKGROUND_BENCHMARK_ID, "南方中证500ETF"
    )
    for etf_id in sorted(required_etfs):
        rows = load_price_series(
            root / "data" / "execution_prices" / asset_file_name(etf_id), "qfq"
        )
        etf_prices[etf_id] = rows
        etf_coverage.append(
            {
                "etf_id": etf_id,
                "name": mapping_name[etf_id],
                "first_date": rows[0]["date"],
                "last_date": rows[-1]["date"],
                "row_count": len(rows),
            }
        )

    research = run_research(assets, research_prices, trade_dates)
    allocation = build_current_allocation(research, assets, mappings, etf_prices)
    shadow = build_shadow(
        research,
        assets,
        mappings,
        etf_prices,
        trade_dates,
        shadow_start_date,
    )
    execution_manifest = load_json(root / "data" / "execution_prices" / "manifest.json")
    data_status = {
        "status": "success",
        "current": True,
        "provider": execution_manifest.get("data_provider", "local"),
        "data_as_of": research["period"]["end"],
        "shadow_start_date": shadow["start_date"],
        "research_index_coverage": index_coverage,
        "etf_coverage": etf_coverage,
        "missing_data": [],
        "duplicate_data": [],
        "invalid_prices": [],
    }
    manifest = {
        "model": MODEL_NAME,
        "model_description": MODEL_DESCRIPTION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "generated_at": execution_manifest.get("generated_at"),
        "provider": data_status["provider"],
        "data_as_of": data_status["data_as_of"],
        "shadow_start_date": shadow["start_date"],
        "reports": sorted(REPORT_NAMES),
    }
    return {
        "research.json": research,
        "allocation.json": allocation,
        "shadow.json": shadow,
        "data_status.json": data_status,
        "manifest.json": manifest,
    }


def _resolve_shadow_start_date(target: Path, requested: str | None) -> str:
    if requested:
        return requested
    for name in ("manifest.json", "data_status.json"):
        path = target / name
        if path.exists():
            value = load_json(path).get("shadow_start_date")
            if value:
                return str(value)
    raise ValueError("first run requires --shadow-start-date YYYY-MM-DD")


def _publish_report_set(target: Path, reports: dict[str, dict]) -> None:
    if set(reports) != REPORT_NAMES:
        raise ValueError("successful current report set must contain exactly five reports")
    stage = Path(tempfile.mkdtemp(prefix="current-stage-", dir=target.parent))
    try:
        for name, value in reports.items():
            (stage / name).write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        _replace_directory(target, stage)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _publish_failure(target: Path, failure: dict) -> None:
    stage = Path(tempfile.mkdtemp(prefix="current-failed-", dir=target.parent))
    try:
        (stage / "data_status.json").write_text(
            json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _replace_directory(target, stage)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _replace_directory(target: Path, stage: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_name(target.name + ".previous")
    if backup.exists():
        shutil.rmtree(backup)
    if target.exists():
        target.replace(backup)
    try:
        stage.replace(target)
    except Exception:
        if backup.exists() and not target.exists():
            backup.replace(target)
        raise
    if backup.exists():
        shutil.rmtree(backup)
