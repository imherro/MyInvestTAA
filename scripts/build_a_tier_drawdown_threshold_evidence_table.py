from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_taa.drawdown_profiles import linear_quantile


LEDGER_RELATIVE = "reports/strategy_research/drawdown_walk_forward_evidence"
OUTPUT_RELATIVE = "reports/strategy_research/drawdown_threshold_evidence_table.json"
HORIZONS = {
    "one_year": 252,
    "two_year": 504,
}


class DrawdownThresholdEvidenceTableBuildError(ValueError):
    pass


def build_drawdown_threshold_evidence_table(
    root: Path, *, generated_at: str | None = None
) -> dict[str, Any]:
    root = Path(root)
    ledger_directory = root / LEDGER_RELATIVE
    index_path = ledger_directory / "index.json"
    index_bytes = index_path.read_bytes()
    index = _load_json(index_bytes, "walk-forward ledger index")
    assets = _validate_index(index)
    expected_names = {"index.json"} | {
        f"{asset['asset_key']}.json" for asset in assets
    }
    actual_names = {path.name for path in ledger_directory.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise DrawdownThresholdEvidenceTableBuildError(
            "walk-forward ledger directory must contain only index and tier A reports"
        )

    rows: list[dict[str, Any]] = []
    blocked_assets: list[dict[str, Any]] = []
    expected_groups: list[tuple[str, str]] | None = None
    for asset in assets:
        report = _load_json(
            (ledger_directory / f"{asset['asset_key']}.json").read_bytes(),
            f"walk-forward ledger report {asset['asset_key']}",
        )
        status = asset["analysis_status"]
        _validate_asset_identity(asset, report)
        if status == "blocked":
            _validate_blocked_report(report)
            blocked_assets.append(
                {
                    "asset_key": asset["asset_key"],
                    "blockers": list(asset["blockers"]),
                }
            )
            continue

        asset_groups, asset_rows = _build_asset_rows(asset, report)
        if expected_groups is None:
            expected_groups = asset_groups
        elif asset_groups != expected_groups:
            raise DrawdownThresholdEvidenceTableBuildError(
                "analyzed asset threshold order differs from the ledger"
            )
        rows.extend(asset_rows)

    if expected_groups is None or len(expected_groups) != 15:
        raise DrawdownThresholdEvidenceTableBuildError(
            "analyzed ledger reports must contain fifteen threshold groups"
        )
    if len(rows) != 75:
        raise DrawdownThresholdEvidenceTableBuildError(
            "compact evidence table must contain exactly seventy-five rows"
        )

    result = {
        "schema_version": "1.0",
        "report_type": "a_tier_compact_drawdown_threshold_evidence_table",
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "source_ledger_index_sha256": hashlib.sha256(index_bytes).hexdigest(),
        "summary": {
            "tier_a_assets": len(assets),
            "analyzed_assets": sum(
                asset["analysis_status"] == "analyzed" for asset in assets
            ),
            "blocked_assets": sum(
                asset["analysis_status"] == "blocked" for asset in assets
            ),
            "threshold_rows": len(rows),
        },
        "blocked_assets": blocked_assets,
        "rows": rows,
    }
    _validate_finite(result)
    return result


def publish_drawdown_threshold_evidence_table(target: Path, report: dict[str, Any]) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=target.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    try:
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_index(index: dict[str, Any]) -> list[dict[str, Any]]:
    assets = index.get("assets")
    summary = index.get("summary")
    if not isinstance(assets, list) or not isinstance(summary, dict) or len(assets) != 7:
        raise DrawdownThresholdEvidenceTableBuildError(
            "walk-forward ledger index must contain seven tier A assets"
        )
    statuses = [asset.get("analysis_status") for asset in assets]
    if statuses.count("analyzed") != 5 or statuses.count("blocked") != 2:
        raise DrawdownThresholdEvidenceTableBuildError(
            "walk-forward ledger index must contain five analyzed and two blocked assets"
        )
    if summary.get("tier_a_assets") != 7 or summary.get("analyzed_assets") != 5 or summary.get("blocked_assets") != 2:
        raise DrawdownThresholdEvidenceTableBuildError(
            "walk-forward ledger index summary is invalid"
        )
    for asset in assets:
        if not all(isinstance(asset.get(field), str) and asset[field] for field in (
            "asset_key", "display_name", "risk_family", "analysis_status", "report_path"
        )) or not isinstance(asset.get("blockers"), list):
            raise DrawdownThresholdEvidenceTableBuildError(
                "walk-forward ledger index asset is invalid"
            )
        if Path(asset["report_path"]).name != f"{asset['asset_key']}.json":
            raise DrawdownThresholdEvidenceTableBuildError(
                "walk-forward ledger index report path is invalid"
            )
    return assets


def _validate_asset_identity(asset: dict[str, Any], report: dict[str, Any]) -> None:
    report_asset = report.get("asset")
    if not isinstance(report_asset, dict) or report.get("analysis_status") != asset["analysis_status"]:
        raise DrawdownThresholdEvidenceTableBuildError("ledger asset status differs from index")
    for field in ("asset_key", "display_name", "risk_family"):
        if report_asset.get(field) != asset[field]:
            raise DrawdownThresholdEvidenceTableBuildError("ledger asset identity differs from index")


def _validate_blocked_report(report: dict[str, Any]) -> None:
    if report.get("event_evaluations") != [] or report.get("summary", {}).get("event_count") != 0:
        raise DrawdownThresholdEvidenceTableBuildError("blocked ledger report must contain no events")


def _build_asset_rows(
    asset: dict[str, Any], report: dict[str, Any]
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    events = report.get("event_evaluations")
    if not isinstance(events, list) or not events:
        raise DrawdownThresholdEvidenceTableBuildError("analyzed ledger report must contain events")
    expected_groups: list[tuple[str, str]] | None = None
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for sequence, event in enumerate(events, start=1):
        if event.get("event_sequence") != sequence or not isinstance(
            event.get("event_completed_in_source"), bool
        ):
            raise DrawdownThresholdEvidenceTableBuildError("ledger event identity is invalid")
        evaluations = event.get("threshold_evaluations")
        if not isinstance(evaluations, list) or len(evaluations) != 15:
            raise DrawdownThresholdEvidenceTableBuildError(
                "ledger event must contain fifteen threshold evaluations"
            )
        groups = [
            (evaluation.get("threshold_family"), evaluation.get("threshold_level"))
            for evaluation in evaluations
        ]
        if any(not isinstance(family, str) or not isinstance(level, str) for family, level in groups):
            raise DrawdownThresholdEvidenceTableBuildError("ledger threshold identity is invalid")
        if expected_groups is None:
            expected_groups = groups
        elif groups != expected_groups:
            raise DrawdownThresholdEvidenceTableBuildError(
                "ledger threshold order differs between events"
            )
        for group, evaluation in zip(groups, evaluations, strict=True):
            _validate_evaluation(event, evaluation)
            grouped.setdefault(group, []).append({"event": event, "evaluation": evaluation})

    assert expected_groups is not None
    rows = [_summarize_group(asset, family, level, grouped[(family, level)]) for family, level in expected_groups]
    return expected_groups, rows


def _validate_evaluation(event: dict[str, Any], evaluation: dict[str, Any]) -> None:
    cohort = evaluation.get("test_cohort")
    if not isinstance(cohort, dict):
        raise DrawdownThresholdEvidenceTableBuildError("ledger test cohort is invalid")
    status = cohort.get("threshold_status")
    outcome = evaluation.get("test_outcome")
    if status not in {"reached", "not_reached", "insufficient_history"}:
        raise DrawdownThresholdEvidenceTableBuildError("ledger threshold status is invalid")
    if (status == "reached") != isinstance(outcome, dict):
        raise DrawdownThresholdEvidenceTableBuildError("ledger threshold outcome state is invalid")
    depth = cohort.get("threshold_depth")
    if depth is not None and (not _is_finite_number(depth) or depth <= 0):
        raise DrawdownThresholdEvidenceTableBuildError("ledger threshold depth must be positive")
    if outcome is not None:
        _validate_outcome(outcome)


def _validate_outcome(outcome: dict[str, Any]) -> None:
    horizons = outcome.get("horizons")
    minimum = outcome.get("minimum_outcome")
    if not isinstance(horizons, list) or not isinstance(minimum, dict):
        raise DrawdownThresholdEvidenceTableBuildError("ledger outcome is invalid")
    by_sessions = {horizon.get("horizon_sessions"): horizon for horizon in horizons}
    if len(by_sessions) != len(horizons) or not all(session in by_sessions for session in HORIZONS.values()):
        raise DrawdownThresholdEvidenceTableBuildError("ledger outcome horizons are invalid")
    for session in HORIZONS.values():
        horizon = by_sessions[session]
        if horizon.get("status") not in {"observed", "censored"}:
            raise DrawdownThresholdEvidenceTableBuildError("ledger horizon status is invalid")
        if horizon["status"] == "observed" and not _is_finite_number(horizon.get("forward_return")):
            raise DrawdownThresholdEvidenceTableBuildError("observed forward return is invalid")
    if minimum.get("status") not in {"realized", "censored"}:
        raise DrawdownThresholdEvidenceTableBuildError("ledger minimum outcome status is invalid")
    if minimum["status"] == "realized" and not _is_finite_number(
        minimum.get("additional_return_from_trigger")
    ):
        raise DrawdownThresholdEvidenceTableBuildError("realized additional return is invalid")


def _summarize_group(
    asset: dict[str, Any], family: str, level: str, entries: list[dict[str, Any]]
) -> dict[str, Any]:
    first = entries[0]["evaluation"]
    depths: list[float] = []
    attained = {
        "event_count": len(entries),
        "insufficient_history_count": 0,
        "reached_count": 0,
        "completed_not_reached_count": 0,
        "open_not_reached_unresolved_count": 0,
    }
    horizon_data = {
        name: {"reached_count": 0, "observed_count": 0, "censored_count": 0, "returns": []}
        for name in HORIZONS
    }
    loss_data = {"reached_count": 0, "realized_count": 0, "censored_count": 0, "losses": []}
    for entry in entries:
        event = entry["event"]
        evaluation = entry["evaluation"]
        cohort = evaluation["test_cohort"]
        depth = cohort["threshold_depth"]
        if depth is not None:
            depths.append(float(depth))
        status = cohort["threshold_status"]
        if status == "insufficient_history":
            attained["insufficient_history_count"] += 1
            continue
        if status == "not_reached":
            key = (
                "completed_not_reached_count"
                if event["event_completed_in_source"]
                else "open_not_reached_unresolved_count"
            )
            attained[key] += 1
            continue

        attained["reached_count"] += 1
        outcome = evaluation["test_outcome"]
        assert isinstance(outcome, dict)
        by_sessions = {horizon["horizon_sessions"]: horizon for horizon in outcome["horizons"]}
        for name, sessions in HORIZONS.items():
            result = horizon_data[name]
            result["reached_count"] += 1
            horizon = by_sessions[sessions]
            if horizon["status"] == "observed":
                forward_return = float(horizon["forward_return"])
                result["observed_count"] += 1
                result["returns"].append(forward_return)
            else:
                result["censored_count"] += 1
        loss_data["reached_count"] += 1
        minimum = outcome["minimum_outcome"]
        if minimum["status"] == "realized":
            loss_data["realized_count"] += 1
            loss_data["losses"].append(
                max(0.0, -float(minimum["additional_return_from_trigger"]))
            )
        else:
            loss_data["censored_count"] += 1

    resolved = attained["reached_count"] + attained["completed_not_reached_count"]
    return {
        "asset_key": asset["asset_key"],
        "display_name": asset["display_name"],
        "risk_family": asset["risk_family"],
        "threshold_family": family,
        "threshold_level": level,
        "threshold_probability_or_fraction": first["threshold_probability_or_fraction"],
        **attained,
        "resolved_attainment_count": resolved,
        "observed_attainment_rate": _ratio(attained["reached_count"], resolved),
        "latest_threshold_depth": depths[-1] if depths else None,
        "median_threshold_depth": linear_quantile(depths, 0.50),
        "one_year": _summarize_horizon(horizon_data["one_year"]),
        "two_year": _summarize_horizon(horizon_data["two_year"]),
        "post_trigger_additional_loss": {
            "reached_count": loss_data["reached_count"],
            "realized_count": loss_data["realized_count"],
            "censored_count": loss_data["censored_count"],
            "median_additional_loss": linear_quantile(loss_data["losses"], 0.50),
            "p75_additional_loss": linear_quantile(loss_data["losses"], 0.75),
        },
    }


def _summarize_horizon(values: dict[str, Any]) -> dict[str, Any]:
    returns = values["returns"]
    observed = values["observed_count"]
    return {
        "reached_count": values["reached_count"],
        "observed_count": observed,
        "censored_count": values["censored_count"],
        "median_forward_return": linear_quantile(returns, 0.50),
        "positive_return_count": sum(value > 0 for value in returns),
        "positive_return_rate": _ratio(sum(value > 0 for value in returns), observed),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _load_json(payload: bytes, description: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DrawdownThresholdEvidenceTableBuildError(
            f"{description} is not valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise DrawdownThresholdEvidenceTableBuildError(f"{description} must be an object")
    return value


def _validate_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise DrawdownThresholdEvidenceTableBuildError("output must contain only finite numbers")
    if isinstance(value, dict):
        for nested in value.values():
            _validate_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _validate_finite(nested)


def main() -> int:
    report = build_drawdown_threshold_evidence_table(ROOT)
    publish_drawdown_threshold_evidence_table(ROOT / OUTPUT_RELATIVE, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
