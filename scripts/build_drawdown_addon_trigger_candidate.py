from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_RELATIVE = (
    "reports/strategy_research/drawdown_threshold_evidence_table.json"
)
OUTPUT_RELATIVE = (
    "reports/strategy_research/drawdown_addon_trigger_candidate_v1.json"
)
SOURCE_REPORT_TYPE = "a_tier_compact_drawdown_threshold_evidence_table"
OUTPUT_REPORT_TYPE = "a_tier_drawdown_addon_trigger_candidate"
THRESHOLD_FAMILY = "completed_event_depth_quantile"
TIER_LEVELS = ((1, "p75"), (2, "p90"), (3, "p95"))
TIER_LEVEL_SET = frozenset(level for _, level in TIER_LEVELS)
EVIDENCE_OBJECT_FIELDS = (
    "one_year",
    "two_year",
    "post_trigger_additional_loss",
)


class DrawdownAddonTriggerCandidateBuildError(ValueError):
    pass


def build_drawdown_addon_trigger_candidate(
    root: Path, *, generated_at: str | None = None
) -> dict[str, Any]:
    root = Path(root)
    source_path = root / SOURCE_RELATIVE
    source_bytes = source_path.read_bytes()
    source = _load_json(source_bytes)
    rows, blocked_assets = _validate_source(source)

    rows_by_asset: dict[str, list[dict[str, Any]]] = {}
    asset_order: list[str] = []
    for row in rows:
        asset_key = row["asset_key"]
        if asset_key not in rows_by_asset:
            rows_by_asset[asset_key] = []
            asset_order.append(asset_key)
        rows_by_asset[asset_key].append(row)

    if len(asset_order) != 5:
        raise DrawdownAddonTriggerCandidateBuildError(
            "source must contain exactly five analyzed assets"
        )

    assets = [
        _build_asset(asset_key, rows_by_asset[asset_key])
        for asset_key in asset_order
    ]
    result = {
        "schema_version": "1.0",
        "report_type": OUTPUT_REPORT_TYPE,
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "source_evidence_table_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_ledger_index_sha256": source["source_ledger_index_sha256"],
        "rule": {
            "threshold_family": THRESHOLD_FAMILY,
            "tiers": [
                {"tier": tier, "threshold_level": level}
                for tier, level in TIER_LEVELS
            ],
            "thresholds_computed_at_event_peak": True,
            "thresholds_frozen_within_event": True,
            "trigger_on_first_reach_or_exceed": True,
            "trigger_once_per_event": True,
            "deeper_tier_preserves_shallower_tiers": True,
            "reset_on_peak_recovery": True,
            "insufficient_history_disables_tier": True,
        },
        "assets": assets,
        "blocked_assets": copy.deepcopy(blocked_assets),
    }
    _validate_result(result, source)
    _validate_finite(result)
    return result


def publish_drawdown_addon_trigger_candidate(
    target: Path, report: dict[str, Any]
) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=target.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(
            report,
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        handle.write("\n")
    try:
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_source(
    source: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if source.get("report_type") != SOURCE_REPORT_TYPE:
        raise DrawdownAddonTriggerCandidateBuildError(
            "source report type is invalid"
        )
    ledger_hash = source.get("source_ledger_index_sha256")
    if not isinstance(ledger_hash, str) or not ledger_hash:
        raise DrawdownAddonTriggerCandidateBuildError(
            "source ledger index hash is required"
        )
    rows = source.get("rows")
    blocked_assets = source.get("blocked_assets")
    if not isinstance(rows, list) or len(rows) != 75:
        raise DrawdownAddonTriggerCandidateBuildError(
            "source must contain exactly seventy-five rows"
        )
    if not isinstance(blocked_assets, list) or len(blocked_assets) != 2:
        raise DrawdownAddonTriggerCandidateBuildError(
            "source must contain exactly two blocked assets"
        )
    for blocked in blocked_assets:
        if set(blocked) != {"asset_key", "blockers"} or not isinstance(
            blocked.get("asset_key"), str
        ) or not isinstance(blocked.get("blockers"), list):
            raise DrawdownAddonTriggerCandidateBuildError(
                "blocked asset shape is invalid"
            )

    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("asset_key"), str):
            raise DrawdownAddonTriggerCandidateBuildError("source row is invalid")
        counts[row["asset_key"]] = counts.get(row["asset_key"], 0) + 1
    if len(counts) != 5 or any(count != 15 for count in counts.values()):
        raise DrawdownAddonTriggerCandidateBuildError(
            "source must contain five analyzed assets with fifteen rows each"
        )
    return rows, blocked_assets


def _build_asset(asset_key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("threshold_family") != THRESHOLD_FAMILY:
            continue
        level = row.get("threshold_level")
        if level in TIER_LEVEL_SET:
            if level in selected:
                raise DrawdownAddonTriggerCandidateBuildError(
                    f"duplicate {THRESHOLD_FAMILY} {level} row for {asset_key}"
                )
            selected[level] = row

    if set(selected) != TIER_LEVEL_SET:
        raise DrawdownAddonTriggerCandidateBuildError(
            f"missing fixed trigger tier for {asset_key}"
        )

    identity = selected["p75"]
    for row in selected.values():
        if any(
            row.get(field) != identity.get(field)
            for field in ("asset_key", "display_name", "risk_family")
        ):
            raise DrawdownAddonTriggerCandidateBuildError(
                f"tier identity differs for {asset_key}"
            )

    tiers = [
        _copy_tier(tier, level, selected[level]) for tier, level in TIER_LEVELS
    ]
    depths = [tier["current_reference_depth"] for tier in tiers]
    if not all(
        _is_finite_number(depth) for depth in depths
    ) or not all(left < right for left, right in zip(depths, depths[1:])):
        raise DrawdownAddonTriggerCandidateBuildError(
            f"current reference depths must increase strictly for {asset_key}"
        )
    return {
        "asset_key": identity["asset_key"],
        "display_name": identity["display_name"],
        "risk_family": identity["risk_family"],
        "tiers": tiers,
    }


def _copy_tier(tier: int, level: str, row: dict[str, Any]) -> dict[str, Any]:
    for field in (
        "latest_threshold_depth",
        "median_threshold_depth",
        "reached_count",
        "resolved_attainment_count",
        "observed_attainment_rate",
        *EVIDENCE_OBJECT_FIELDS,
    ):
        if field not in row:
            raise DrawdownAddonTriggerCandidateBuildError(
                f"source row is missing evidence field {field}"
            )
    if any(not isinstance(row[field], dict) for field in EVIDENCE_OBJECT_FIELDS):
        raise DrawdownAddonTriggerCandidateBuildError(
            "source horizon or loss evidence must be an object"
        )
    return {
        "tier": tier,
        "threshold_family": THRESHOLD_FAMILY,
        "threshold_level": level,
        "current_reference_depth": row["latest_threshold_depth"],
        "median_historical_depth": row["median_threshold_depth"],
        "reached_count": row["reached_count"],
        "resolved_attainment_count": row["resolved_attainment_count"],
        "observed_attainment_rate": row["observed_attainment_rate"],
        "one_year": copy.deepcopy(row["one_year"]),
        "two_year": copy.deepcopy(row["two_year"]),
        "post_trigger_additional_loss": copy.deepcopy(
            row["post_trigger_additional_loss"]
        ),
    }


def _validate_result(result: dict[str, Any], source: dict[str, Any]) -> None:
    assets = result["assets"]
    if len(assets) != 5 or sum(len(asset["tiers"]) for asset in assets) != 15:
        raise DrawdownAddonTriggerCandidateBuildError(
            "output must contain five assets and fifteen tiers"
        )
    source_rows = {
        (row["asset_key"], row["threshold_family"], row["threshold_level"]): row
        for row in source["rows"]
    }
    for asset in assets:
        for tier in asset["tiers"]:
            source_row = source_rows[
                (asset["asset_key"], tier["threshold_family"], tier["threshold_level"])
            ]
            if tier["current_reference_depth"] != source_row["latest_threshold_depth"]:
                raise DrawdownAddonTriggerCandidateBuildError(
                    "current reference depth differs from source"
                )
            if tier["median_historical_depth"] != source_row["median_threshold_depth"]:
                raise DrawdownAddonTriggerCandidateBuildError(
                    "median historical depth differs from source"
                )
            for field in (
                "reached_count",
                "resolved_attainment_count",
                "observed_attainment_rate",
                *EVIDENCE_OBJECT_FIELDS,
            ):
                if tier[field] != source_row[field]:
                    raise DrawdownAddonTriggerCandidateBuildError(
                        f"tier evidence field {field} differs from source"
                    )


def _load_json(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DrawdownAddonTriggerCandidateBuildError(
            "source evidence table is not valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise DrawdownAddonTriggerCandidateBuildError(
            "source evidence table must be an object"
        )
    return value


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _validate_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise DrawdownAddonTriggerCandidateBuildError(
            "output must contain only finite numbers"
        )
    if isinstance(value, dict):
        for nested in value.values():
            _validate_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _validate_finite(nested)


def main() -> int:
    report = build_drawdown_addon_trigger_candidate(ROOT)
    publish_drawdown_addon_trigger_candidate(ROOT / OUTPUT_RELATIVE, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
