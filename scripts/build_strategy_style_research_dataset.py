from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_RELATIVE = "config/strategy_style_research_universe_v1.json"
DATASET_RELATIVE = "data/strategy_style_research"
REPORT_RELATIVE = (
    "reports/strategy_research/strategy_style_data_qualification_v1.json"
)
FORMAL_AS_OF = "2026-07-15"
METADATA_FIELDS = (
    "ts_code",
    "name",
    "fullname",
    "market",
    "category",
    "base_date",
    "list_date",
)
STYLE_FAMILIES = ("growth", "value", "dividend", "cash_flow")
EXPECTED_STYLE_COUNTS = {
    "growth": 1,
    "value": 1,
    "dividend": 2,
    "cash_flow": 1,
}
FORBIDDEN_OUTPUT_TERMS = (
    "token",
    "access_token",
    "tushare_token",
    "authorization",
)


class StrategyStyleDatasetError(ValueError):
    pass


class StrategyStyleDatasetBlocked(StrategyStyleDatasetError):
    pass


class RecordsProvider(Protocol):
    def index_basic(self, *, ts_code: str, fields: str) -> list[dict[str, Any]]: ...

    def index_daily(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
        fields: str,
    ) -> list[dict[str, Any]]: ...

    def trade_cal(
        self,
        *,
        exchange: str,
        is_open: str,
        start_date: str,
        end_date: str,
        fields: str,
    ) -> list[dict[str, Any]]: ...


class TushareRecordsProvider:
    def __init__(self, token: str) -> None:
        if not token:
            raise StrategyStyleDatasetError("TUSHARE_TOKEN is required")
        try:
            import tushare as ts
        except ImportError as exc:
            raise StrategyStyleDatasetError("tushare package is not installed") from exc
        ts.set_token(token)
        self._client = ts.pro_api()

    def index_basic(self, *, ts_code: str, fields: str) -> list[dict[str, Any]]:
        return _records(self._client.index_basic(ts_code=ts_code, fields=fields))

    def index_daily(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
        fields: str,
    ) -> list[dict[str, Any]]:
        return _records(
            self._client.index_daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=fields,
            )
        )

    def trade_cal(
        self,
        *,
        exchange: str,
        is_open: str,
        start_date: str,
        end_date: str,
        fields: str,
    ) -> list[dict[str, Any]]:
        return _records(
            self._client.trade_cal(
                exchange=exchange,
                is_open=is_open,
                start_date=start_date,
                end_date=end_date,
                fields=fields,
            )
        )


@dataclass(frozen=True)
class AssetSnapshot:
    config: dict[str, Any]
    metadata: dict[str, str]
    prices: list[dict[str, Any]]
    query_start_date: str
    query_end_date: str
    query_chunk_count: int

    @property
    def asset_id(self) -> str:
        return self.config["asset_id"]

    @property
    def first_date(self) -> str:
        return self.prices[0]["date"]

    @property
    def last_date(self) -> str:
        return self.prices[-1]["date"]


def build_strategy_style_research_dataset(
    root: Path,
    *,
    as_of: str,
    provider: RecordsProvider | None = None,
    generated_at: str | None = None,
    publish: bool = True,
) -> dict[str, Any]:
    root = Path(root)
    _validate_iso_date(as_of, "as_of")
    universe_path = root / UNIVERSE_RELATIVE
    universe_bytes = universe_path.read_bytes()
    universe = _load_json_object(universe_bytes, "universe config")
    assets = validate_universe_config(universe)
    resolved_provider = provider or TushareRecordsProvider(_load_token(root))
    generated = generated_at or datetime.now(UTC).isoformat(timespec="seconds")

    snapshots = [
        download_asset_snapshot(asset, as_of, resolved_provider)
        for asset in assets
    ]
    earliest_date = min(snapshot.first_date for snapshot in snapshots)
    calendar_dates, calendar_chunk_count = download_trade_calendar(
        earliest_date, as_of, resolved_provider
    )
    calendar = {
        "schema_version": "1.0",
        "exchange": "SSE",
        "source": "tushare.trade_cal",
        "as_of_date": as_of,
        "first_date": calendar_dates[0],
        "last_date": calendar_dates[-1],
        "query_chunk_count": calendar_chunk_count,
        "dates": calendar_dates,
    }
    calendar_bytes = _json_bytes(calendar)

    price_bytes = {
        snapshot.asset_id: _json_bytes(snapshot.prices) for snapshot in snapshots
    }
    universe_hash = hashlib.sha256(universe_bytes).hexdigest()
    calendar_hash = hashlib.sha256(calendar_bytes).hexdigest()
    manifest = _build_manifest(
        snapshots,
        price_bytes,
        generated_at=generated,
        as_of=as_of,
        universe_hash=universe_hash,
        calendar_hash=calendar_hash,
    )
    manifest_bytes = _json_bytes(manifest)
    report = build_qualification_report(
        snapshots,
        calendar,
        manifest,
        price_bytes,
        generated_at=generated,
        as_of=as_of,
        universe_hash=universe_hash,
        manifest_hash=hashlib.sha256(manifest_bytes).hexdigest(),
        universe=universe,
    )
    if report["overall_status"] != "QUALIFIED":
        blockers = [
            f"{row['asset_id']}: {', '.join(row['blockers'])}"
            for row in report["assets"]
            if not row["qualified"]
        ]
        raise StrategyStyleDatasetBlocked("; ".join(blockers))

    output_bytes = {
        "manifest.json": manifest_bytes,
        "sse_trade_calendar.json": calendar_bytes,
        **{
            f"prices/{_price_filename(asset_id)}": content
            for asset_id, content in price_bytes.items()
        },
    }
    report_bytes = _json_bytes(report)
    _validate_output_boundary(output_bytes, report_bytes)
    if publish:
        publish_snapshot(root, output_bytes, report_bytes)
    return report


def validate_universe_config(universe: dict[str, Any]) -> list[dict[str, Any]]:
    expected_top = {
        "schema_version": "1.0",
        "universe_id": "STRATEGY_STYLE_RESEARCH_UNIVERSE_V1",
        "purpose": "independent_strategy_style_research",
        "required_data_source": "tushare",
        "required_return_basis": "total_return",
        "cache_policy": "full_independent_snapshot",
        "allowed_style_families": list(STYLE_FAMILIES),
        "excluded_scope": [
            "broad_base",
            "industry_theme",
            "resource_cycle",
            "other_assets",
        ],
    }
    if any(universe.get(key) != value for key, value in expected_top.items()):
        raise StrategyStyleDatasetError("strategy-style universe header is invalid")
    assets = universe.get("assets")
    if not isinstance(assets, list) or len(assets) != 5:
        raise StrategyStyleDatasetError("strategy-style universe must contain five assets")
    if [asset.get("research_order") for asset in assets] != [1, 2, 3, 4, 5]:
        raise StrategyStyleDatasetError("research order must be 1 through 5")
    asset_ids = [asset.get("asset_id") for asset in assets]
    if len(set(asset_ids)) != len(asset_ids):
        raise StrategyStyleDatasetError("strategy-style asset IDs must be unique")
    style_counts = {
        family: sum(asset.get("style_family") == family for asset in assets)
        for family in STYLE_FAMILIES
    }
    if style_counts != EXPECTED_STYLE_COUNTS:
        raise StrategyStyleDatasetError("strategy-style family counts are invalid")
    for asset in assets:
        asset_id = asset.get("asset_id")
        official_code = asset.get("official_code")
        if (
            not isinstance(asset_id, str)
            or not isinstance(official_code, str)
            or asset_id.split(".", 1)[0] != official_code
        ):
            raise StrategyStyleDatasetError("asset identity is invalid")
        if asset.get("metadata_expectation_mode") not in {"exact", "identity_only"}:
            raise StrategyStyleDatasetError("metadata expectation mode is invalid")
        if asset.get("metadata_expectation_mode") == "exact":
            expected = asset.get("expected_index_basic")
            if not isinstance(expected, dict) or set(expected) != set(METADATA_FIELDS[1:]):
                raise StrategyStyleDatasetError("exact metadata expectation is invalid")
        elif asset.get("expected_index_basic") is not None:
            raise StrategyStyleDatasetError("identity-only metadata expectation must be null")
        fixed = {
            "data_source": "tushare",
            "return_basis": "total_return",
            "enabled": True,
            "substitution_allowed": False,
        }
        if any(asset.get(key) != value for key, value in fixed.items()):
            raise StrategyStyleDatasetError("fixed asset properties are invalid")
    return assets


def download_asset_snapshot(
    asset: dict[str, Any], as_of: str, provider: RecordsProvider
) -> AssetSnapshot:
    asset_id = asset["asset_id"]
    metadata_rows = provider.index_basic(
        ts_code=asset_id, fields=",".join(METADATA_FIELDS)
    )
    metadata = validate_index_basic(asset, metadata_rows)
    chunks = year_chunks(metadata["base_date"][:4], as_of)
    raw_rows: list[dict[str, Any]] = []
    for start_date, end_date in chunks:
        raw_rows.extend(
            provider.index_daily(
                ts_code=asset_id,
                start_date=start_date,
                end_date=end_date,
                fields="ts_code,trade_date,close",
            )
        )
    prices = validate_price_rows(asset_id, raw_rows, as_of)
    return AssetSnapshot(
        config=asset,
        metadata=metadata,
        prices=prices,
        query_start_date=chunks[0][0],
        query_end_date=as_of,
        query_chunk_count=len(chunks),
    )


def validate_index_basic(
    asset: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, str]:
    if len(rows) != 1:
        raise StrategyStyleDatasetError(
            f"index_basic must return one row for {asset['asset_id']}"
        )
    row = rows[0]
    metadata: dict[str, str] = {}
    for field in METADATA_FIELDS:
        value = row.get(field)
        if value is None or not str(value).strip() or str(value).lower() == "nan":
            raise StrategyStyleDatasetError(
                f"index_basic field {field} is missing for {asset['asset_id']}"
            )
        metadata[field] = str(value).strip()
    if metadata["ts_code"] != asset["asset_id"]:
        raise StrategyStyleDatasetError("index_basic ts_code differs from configuration")
    if metadata["ts_code"].split(".", 1)[0] != asset["official_code"]:
        raise StrategyStyleDatasetError("index_basic official code differs")
    _validate_compact_date(metadata["base_date"], "base_date")
    _validate_compact_date(metadata["list_date"], "list_date")
    if asset["metadata_expectation_mode"] == "exact":
        expected = asset["expected_index_basic"]
        if any(metadata[field] != expected[field] for field in METADATA_FIELDS[1:]):
            raise StrategyStyleDatasetError(
                f"exact index_basic metadata differs for {asset['asset_id']}"
            )
    return metadata


def validate_price_rows(
    asset_id: str, raw_rows: list[dict[str, Any]], as_of: str
) -> list[dict[str, Any]]:
    if not raw_rows:
        raise StrategyStyleDatasetError(f"price history is empty for {asset_id}")
    compact_as_of = as_of.replace("-", "")
    raw_dates = [str(row.get("trade_date", "")) for row in raw_rows]
    duplicates = _duplicate_values(raw_dates)
    if duplicates:
        raise StrategyStyleDatasetError(
            f"duplicate price date for {asset_id}: {duplicates[0]}"
        )
    prices = []
    for row in raw_rows:
        if row.get("ts_code") not in {None, asset_id}:
            raise StrategyStyleDatasetError(f"price ts_code differs for {asset_id}")
        trade_date = str(row.get("trade_date", ""))
        _validate_compact_date(trade_date, "trade_date")
        if trade_date > compact_as_of:
            raise StrategyStyleDatasetError(f"future price date for {asset_id}")
        close = row.get("close")
        if (
            not isinstance(close, (int, float))
            or isinstance(close, bool)
            or not math.isfinite(float(close))
            or float(close) <= 0
        ):
            raise StrategyStyleDatasetError(f"invalid close for {asset_id}")
        prices.append(
            {
                "date": _iso_date(trade_date),
                "close": float(close),
                "return_basis": "total_return",
            }
        )
    prices.sort(key=lambda row: row["date"])
    return prices


def download_trade_calendar(
    first_date: str, as_of: str, provider: RecordsProvider
) -> tuple[list[str], int]:
    chunks = year_chunks(first_date[:4], as_of)
    raw_rows: list[dict[str, Any]] = []
    compact_first = first_date.replace("-", "")
    for start_date, end_date in chunks:
        query_start = max(start_date, compact_first)
        raw_rows.extend(
            provider.trade_cal(
                exchange="SSE",
                is_open="1",
                start_date=query_start,
                end_date=end_date,
                fields="cal_date,is_open",
            )
        )
    compact_dates = [
        str(row.get("cal_date", ""))
        for row in raw_rows
        if str(row.get("is_open", "1")) == "1"
    ]
    duplicates = _duplicate_values(compact_dates)
    if duplicates:
        raise StrategyStyleDatasetError(
            f"duplicate calendar date: {duplicates[0]}"
        )
    if not compact_dates:
        raise StrategyStyleDatasetError("SSE trade calendar is empty")
    for compact_date in compact_dates:
        _validate_compact_date(compact_date, "cal_date")
    dates = sorted(_iso_date(value) for value in compact_dates)
    if dates[0] != first_date or dates[-1] != as_of:
        raise StrategyStyleDatasetError("SSE calendar does not cover full dataset")
    return dates, len(chunks)


def year_chunks(start_year: str, as_of: str) -> list[tuple[str, str]]:
    if not start_year.isdigit() or len(start_year) != 4:
        raise StrategyStyleDatasetError("start year is invalid")
    end_year = int(as_of[:4])
    first_year = int(start_year)
    if first_year > end_year:
        raise StrategyStyleDatasetError("start year is after as_of")
    compact_as_of = as_of.replace("-", "")
    return [
        (
            f"{year}0101",
            min(f"{year}1231", compact_as_of),
        )
        for year in range(first_year, end_year + 1)
    ]


def build_qualification_report(
    snapshots: list[AssetSnapshot],
    calendar: dict[str, Any],
    manifest: dict[str, Any],
    price_bytes: dict[str, bytes],
    *,
    generated_at: str,
    as_of: str,
    universe_hash: str,
    manifest_hash: str,
    universe: dict[str, Any],
) -> dict[str, Any]:
    manifest_assets = {row["asset_id"]: row for row in manifest["assets"]}
    rows = [
        qualify_asset(
            snapshot,
            calendar,
            manifest_assets[snapshot.asset_id],
            price_bytes[snapshot.asset_id],
        )
        for snapshot in snapshots
    ]
    qualified_count = sum(row["qualified"] for row in rows)
    summary = {
        "total_assets": len(rows),
        "qualified_assets": qualified_count,
        "blocked_assets": len(rows) - qualified_count,
        "growth_assets": EXPECTED_STYLE_COUNTS["growth"],
        "value_assets": EXPECTED_STYLE_COUNTS["value"],
        "dividend_assets": EXPECTED_STYLE_COUNTS["dividend"],
        "cash_flow_assets": EXPECTED_STYLE_COUNTS["cash_flow"],
    }
    return {
        "schema_version": "1.0",
        "report_type": "strategy_style_research_data_qualification",
        "generated_at": generated_at,
        "as_of_date": as_of,
        "source_universe_config_sha256": universe_hash,
        "source_manifest_sha256": manifest_hash,
        "summary": summary,
        "overall_status": (
            "QUALIFIED"
            if summary["total_assets"] == 5
            and summary["qualified_assets"] == 5
            and summary["blocked_assets"] == 0
            else "BLOCKED"
        ),
        "scope": {
            "included_style_families": universe["allowed_style_families"],
            "excluded_scope": universe["excluded_scope"],
        },
        "assets": rows,
        "limitations": [
            "Qualification establishes data identity and completeness only.",
            "The dataset is not an input to formal CURRENT_TAA or execution.",
            "No drawdown mechanism, allocation rule, or backtest is defined.",
        ],
    }


def qualify_asset(
    snapshot: AssetSnapshot,
    calendar: dict[str, Any],
    manifest_asset: dict[str, Any],
    serialized_prices: bytes,
) -> dict[str, Any]:
    prices = snapshot.prices
    price_dates = [row["date"] for row in prices]
    expected_dates = [
        value
        for value in calendar["dates"]
        if snapshot.first_date <= value <= calendar["as_of_date"]
    ]
    missing_dates = sorted(set(expected_dates) - set(price_dates))
    extra_dates = sorted(set(price_dates) - set(expected_dates))
    duplicate_count = len(price_dates) - len(set(price_dates))
    metadata_match = (
        snapshot.config["metadata_expectation_mode"] == "identity_only"
        or all(
            snapshot.metadata[field]
            == snapshot.config["expected_index_basic"][field]
            for field in METADATA_FIELDS[1:]
        )
    )
    required_metadata_complete = all(snapshot.metadata.get(field) for field in METADATA_FIELDS)
    valid_closes = all(
        isinstance(row.get("close"), (int, float))
        and not isinstance(row.get("close"), bool)
        and math.isfinite(float(row["close"]))
        and float(row["close"]) > 0
        for row in prices
    )
    checks = {
        "configured_identity_valid": (
            snapshot.asset_id.split(".", 1)[0]
            == snapshot.config["official_code"]
        ),
        "index_basic_single_row": True,
        "index_basic_required_fields_complete": required_metadata_complete,
        "expected_metadata_match": metadata_match,
        "sorted_unique_dates": price_dates == sorted(set(price_dates)),
        "duplicate_date_count_zero": duplicate_count == 0,
        "valid_close_values": valid_closes,
        "return_basis_valid": all(
            row.get("return_basis") == "total_return" for row in prices
        ),
        "ends_at_latest_open_session": (
            bool(price_dates) and price_dates[-1] == calendar["dates"][-1]
        ),
        "exact_sse_calendar_match": (
            not missing_dates and not extra_dates and price_dates == expected_dates
        ),
    }
    hash_matches = (
        hashlib.sha256(serialized_prices).hexdigest()
        == manifest_asset["price_file_sha256"]
    )
    blockers = [name for name, passed in checks.items() if not passed]
    if not hash_matches:
        blockers.append("price_file_sha256_matches_manifest")
    qualified = not blockers and bool(prices)
    return {
        "asset_id": snapshot.asset_id,
        "official_code": snapshot.config["official_code"],
        "display_name": snapshot.config["display_name"],
        "style_family": snapshot.config["style_family"],
        "research_order": snapshot.config["research_order"],
        "index_basic": snapshot.metadata,
        "price_file": manifest_asset["price_file"],
        "price_file_sha256": manifest_asset["price_file_sha256"],
        "first_date": snapshot.first_date,
        "last_date": snapshot.last_date,
        "row_count": len(prices),
        "calendar_coverage": {
            "calendar_first_date": expected_dates[0] if expected_dates else None,
            "calendar_last_date": expected_dates[-1] if expected_dates else None,
            "expected_open_session_count": len(expected_dates),
            "actual_price_session_count": len(price_dates),
            "missing_open_dates": missing_dates,
            "extra_price_dates": extra_dates,
            "exact_calendar_match": not missing_dates and not extra_dates,
        },
        "checks": checks,
        "qualified": qualified,
        "blockers": blockers,
        "warnings": [],
    }


def publish_snapshot(
    root: Path, output_bytes: dict[str, bytes], report_bytes: bytes
) -> None:
    root = Path(root)
    temporary_root = Path(tempfile.mkdtemp(prefix="style-data-stage-", dir=root))
    stage_data = temporary_root / "dataset"
    stage_report = temporary_root / "qualification.json"
    target_data = root / DATASET_RELATIVE
    target_report = root / REPORT_RELATIVE
    backup_data = temporary_root / "previous-dataset"
    backup_report = temporary_root / "previous-qualification.json"
    data_replaced = False
    report_replaced = False
    try:
        for relative, content in output_bytes.items():
            target = stage_data / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        stage_report.write_bytes(report_bytes)
        target_data.parent.mkdir(parents=True, exist_ok=True)
        target_report.parent.mkdir(parents=True, exist_ok=True)
        if target_data.exists():
            os.replace(target_data, backup_data)
        os.replace(stage_data, target_data)
        data_replaced = True
        if target_report.exists():
            os.replace(target_report, backup_report)
        os.replace(stage_report, target_report)
        report_replaced = True
    except Exception:
        if report_replaced and target_report.exists():
            target_report.unlink()
        if backup_report.exists():
            os.replace(backup_report, target_report)
        if data_replaced and target_data.exists():
            shutil.rmtree(target_data)
        if backup_data.exists():
            os.replace(backup_data, target_data)
        raise
    finally:
        if temporary_root.exists():
            shutil.rmtree(temporary_root)


def _build_manifest(
    snapshots: list[AssetSnapshot],
    price_bytes: dict[str, bytes],
    *,
    generated_at: str,
    as_of: str,
    universe_hash: str,
    calendar_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "dataset_id": "STRATEGY_STYLE_RESEARCH_DATASET_V1",
        "generated_at": generated_at,
        "as_of_date": as_of,
        "provider": "tushare",
        "return_basis": "total_return",
        "cache_policy": "full_independent_snapshot",
        "universe_config_path": UNIVERSE_RELATIVE,
        "universe_config_sha256": universe_hash,
        "calendar_path": f"{DATASET_RELATIVE}/sse_trade_calendar.json",
        "calendar_sha256": calendar_hash,
        "query_policy": {
            "metadata_endpoint": "index_basic",
            "price_endpoint": "index_daily",
            "calendar_endpoint": "trade_cal",
            "chunking": "calendar_year",
        },
        "assets": [
            {
                "asset_id": snapshot.asset_id,
                "official_code": snapshot.config["official_code"],
                "display_name": snapshot.config["display_name"],
                "style_family": snapshot.config["style_family"],
                "research_order": snapshot.config["research_order"],
                "metadata_expectation_mode": snapshot.config[
                    "metadata_expectation_mode"
                ],
                "index_basic": snapshot.metadata,
                "price_file": (
                    f"{DATASET_RELATIVE}/prices/{_price_filename(snapshot.asset_id)}"
                ),
                "price_file_sha256": hashlib.sha256(
                    price_bytes[snapshot.asset_id]
                ).hexdigest(),
                "query_start_date": _iso_date(snapshot.query_start_date),
                "query_end_date": snapshot.query_end_date,
                "query_chunk_count": snapshot.query_chunk_count,
                "first_date": snapshot.first_date,
                "last_date": snapshot.last_date,
                "row_count": len(snapshot.prices),
                "return_basis": "total_return",
            }
            for snapshot in snapshots
        ],
    }


def _validate_output_boundary(
    output_bytes: dict[str, bytes], report_bytes: bytes
) -> None:
    expected = {
        "manifest.json",
        "sse_trade_calendar.json",
        "prices/CN2296_CNI.json",
        "prices/CN2371_CNI.json",
        "prices/H00015_CSI.json",
        "prices/H00922_CSI.json",
        "prices/480092_CNI.json",
    }
    if set(output_bytes) != expected:
        raise StrategyStyleDatasetError("dataset output inventory differs")
    combined = b"\n".join([*output_bytes.values(), report_bytes]).lower()
    if any(term.encode("utf-8") in combined for term in FORBIDDEN_OUTPUT_TERMS):
        raise StrategyStyleDatasetError("output contains forbidden authentication term")
    for content in [*output_bytes.values(), report_bytes]:
        json.loads(content.decode("utf-8"))


def _load_token(root: Path) -> str:
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if token:
        return token
    env_path = root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == "TUSHARE_TOKEN":
                token = value.strip().strip('"').strip("'")
                break
    if not token:
        raise StrategyStyleDatasetError("TUSHARE_TOKEN is required")
    return token


def _records(value: Any) -> list[dict[str, Any]]:
    if hasattr(value, "to_dict"):
        records = value.to_dict("records")
    else:
        records = value
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise StrategyStyleDatasetError("provider response must be record rows")
    return records


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _price_filename(asset_id: str) -> str:
    return f"{asset_id.replace('.', '_')}.json"


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _load_json_object(content: bytes, label: str) -> dict[str, Any]:
    value = json.loads(content.decode("utf-8"))
    if not isinstance(value, dict):
        raise StrategyStyleDatasetError(f"{label} must be an object")
    return value


def _validate_iso_date(value: str, label: str) -> None:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise StrategyStyleDatasetError(f"{label} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise StrategyStyleDatasetError(f"{label} must be YYYY-MM-DD")


def _validate_compact_date(value: str, label: str) -> None:
    if len(value) != 8 or not value.isdigit():
        raise StrategyStyleDatasetError(f"{label} must be YYYYMMDD")
    _validate_iso_date(_iso_date(value), label)


def _iso_date(value: str) -> str:
    compact = value.replace("-", "")
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the independent strategy-style research dataset."
    )
    parser.add_argument("--as-of", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        report = build_strategy_style_research_dataset(
            ROOT,
            as_of=args.as_of,
        )
    except StrategyStyleDatasetError as exc:
        print(f"strategy-style dataset build failed: {exc}")
        return 1
    print(
        f"{REPORT_RELATIVE}: {report['overall_status']} "
        f"({report['summary']['qualified_assets']}/5 qualified)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
