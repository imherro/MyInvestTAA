from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_taa.drawdown_outcomes import build_drawdown_outcomes
from current_taa.drawdown_profiles import build_drawdown_profile
from current_taa.research_universe import load_research_universe
from scripts.build_a_tier_drawdown_profiles import (
    AUDIT_RELATIVE,
    EVENT_INDEX_RELATIVE,
    _load_json,
    _replace_directory,
    _validate_event_file_set,
    _validate_event_identity,
    _validate_source_index,
)


OUTPUT_RELATIVE = "reports/strategy_research/drawdown_outcomes"


class DrawdownOutcomeBuildError(ValueError):
    pass


def build_drawdown_outcome_report_set(
    root: Path, *, generated_at: str | None = None
) -> dict[str, dict[str, Any]]:
    root = Path(root)
    universe = load_research_universe(root / "config/research_universe_v1.json")
    tier_a = universe.assets_for_tier("A")
    audit_bytes = (root / AUDIT_RELATIVE).read_bytes()
    event_index_bytes = (root / EVENT_INDEX_RELATIVE).read_bytes()
    audit = _load_json(audit_bytes, "universe audit")
    event_index = _load_json(event_index_bytes, "drawdown event index")
    try:
        _validate_source_index(universe, tier_a, audit_bytes, audit, event_index)
        _validate_event_file_set(root, tier_a)
    except ValueError as exc:
        raise DrawdownOutcomeBuildError(str(exc)) from exc

    index_hash = hashlib.sha256(event_index_bytes).hexdigest()
    source_rows = {row["asset_key"]: row for row in event_index["assets"]}
    reports: dict[str, dict[str, Any]] = {}
    index_assets: list[dict[str, Any]] = []
    analyzed = blocked = total_events = total_records = 0
    completed_events = open_events = 0

    for asset in tier_a:
        relative = f"reports/strategy_research/drawdown_events/{asset.asset_key}.json"
        event_bytes = (root / relative).read_bytes()
        event_report = _load_json(event_bytes, f"event report {asset.asset_key}")
        try:
            _validate_event_identity(
                asset,
                source_rows[asset.asset_key],
                event_report,
                universe.universe_hash,
                event_index,
            )
        except ValueError as exc:
            raise DrawdownOutcomeBuildError(str(exc)) from exc
        if event_report["analysis_status"] == "analyzed":
            build_drawdown_profile(event_report)
            analyzed += 1
        else:
            _validate_blocked(event_report)
            blocked += 1
        body = build_drawdown_outcomes(event_report)
        event_hash = hashlib.sha256(event_bytes).hexdigest()
        total_events += body["summary"]["event_count"]
        completed_events += body["summary"]["completed_event_count"]
        open_events += body["summary"]["open_event_count"]
        total_records += body["summary"]["frontier_record_count"]
        report = {
            "schema_version": "1.0",
            "report_type": "asset_drawdown_frontier_outcomes",
            "methodology_version": "1.0",
            "analysis_status": event_report["analysis_status"],
            "asset": event_report["asset"],
            "universe_id": universe.universe_id,
            "universe_hash": universe.universe_hash,
            "source_event_index_path": EVENT_INDEX_RELATIVE,
            "source_event_index_sha256": index_hash,
            "source_event_report_path": relative,
            "source_event_report_sha256": event_hash,
            "period": body["period"],
            "summary": body["summary"],
            "records": body["records"],
            "blockers": list(event_report.get("blockers", [])),
            "limitations": _limitations(),
        }
        name = f"{asset.asset_key}.json"
        reports[name] = report
        index_assets.append(
            {
                "asset_key": asset.asset_key,
                "display_name": asset.display_name,
                "risk_family": asset.risk_family,
                "analysis_status": report["analysis_status"],
                "report_path": f"{OUTPUT_RELATIVE}/{name}",
                "event_count": body["summary"]["event_count"],
                "frontier_record_count": body["summary"]["frontier_record_count"],
                "source_event_report_sha256": event_hash,
                "blockers": report["blockers"],
            }
        )

    expected_source = {
        "analyzed_assets": analyzed,
        "blocked_assets": blocked,
        "completed_events": completed_events,
        "open_events": open_events,
        "tier_a_assets": 7,
    }
    if any(
        event_index["summary"].get(key) != value
        for key, value in expected_source.items()
    ):
        raise DrawdownOutcomeBuildError(
            "event index summary differs from asset event reports"
        )

    reports["index.json"] = {
        "schema_version": "1.0",
        "report_type": "a_tier_drawdown_frontier_outcome_index",
        "methodology_version": "1.0",
        "universe_id": universe.universe_id,
        "universe_hash": universe.universe_hash,
        "source_event_index_path": EVENT_INDEX_RELATIVE,
        "source_event_index_sha256": index_hash,
        "generated_at": generated_at or datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "tier_a_assets": 7,
            "analyzed_assets": analyzed,
            "blocked_assets": blocked,
            "total_events": total_events,
            "total_frontier_records": total_records,
        },
        "assets": index_assets,
        "limitations": _limitations(),
    }
    expected = {"index.json"} | {f"{asset.asset_key}.json" for asset in tier_a}
    if set(reports) != expected:
        raise DrawdownOutcomeBuildError("outcome report set differs from tier A")
    return reports


def publish_drawdown_outcome_report_set(
    target: Path, reports: dict[str, dict[str, Any]]
) -> None:
    target = Path(target)
    if len(reports) != 8 or "index.json" not in reports:
        raise DrawdownOutcomeBuildError("outcome report set must contain eight files")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="outcome-stage-", dir=target.parent))
    try:
        for name, report in reports.items():
            (stage / name).write_text(
                json.dumps(
                    report,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
        _validate_stage(stage, reports)
        _replace_directory(target, stage)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _validate_blocked(report: dict[str, Any]) -> None:
    if report.get("events") != [] or report.get("drawdown_series") != []:
        raise DrawdownOutcomeBuildError("blocked event report must have empty facts")
    if report.get("current_state") is not None:
        raise DrawdownOutcomeBuildError(
            "blocked event report current state must be null"
        )


def _validate_stage(stage: Path, reports: dict[str, dict[str, Any]]) -> None:
    if {path.name for path in stage.iterdir() if path.is_file()} != set(reports):
        raise DrawdownOutcomeBuildError("staged outcome reports are incomplete")
    loaded = {
        name: json.loads((stage / name).read_text(encoding="utf-8"))
        for name in reports
    }
    index = loaded["index.json"]
    events = records = analyzed = blocked = 0
    for row in index["assets"]:
        report = loaded.get(Path(row["report_path"]).name)
        if report is None or report["asset"]["asset_key"] != row["asset_key"]:
            raise DrawdownOutcomeBuildError("outcome index reference is invalid")
        if report["universe_hash"] != index["universe_hash"] or report[
            "source_event_index_sha256"
        ] != index["source_event_index_sha256"]:
            raise DrawdownOutcomeBuildError("outcome source chain differs from index")
        record_order = [
            (record["event_sequence"], record["frontier_sequence"])
            for record in report["records"]
        ]
        record_ids = [record["record_id"] for record in report["records"]]
        if record_order != sorted(record_order) or len(record_ids) != len(
            set(record_ids)
        ):
            raise DrawdownOutcomeBuildError("outcome records are not stable and unique")
        if report["source_event_report_sha256"] != row["source_event_report_sha256"]:
            raise DrawdownOutcomeBuildError("outcome source report hash differs")
        expected_summary = _summary_from_records(report)
        if report["summary"] != expected_summary:
            raise DrawdownOutcomeBuildError("outcome summary differs from records")
        events += report["summary"]["event_count"]
        records += report["summary"]["frontier_record_count"]
        analyzed += report["analysis_status"] == "analyzed"
        blocked += report["analysis_status"] == "blocked"
    expected = {
        "tier_a_assets": 7,
        "analyzed_assets": analyzed,
        "blocked_assets": blocked,
        "total_events": events,
        "total_frontier_records": records,
    }
    if index["summary"] != expected:
        raise DrawdownOutcomeBuildError("outcome index summary differs from reports")


def _summary_from_records(report: dict[str, Any]) -> dict[str, int]:
    records = report["records"]
    event_states = {
        record["event_id"]: record["event_completed_in_source"] for record in records
    }
    return {
        "event_count": len(event_states),
        "completed_event_count": sum(event_states.values()),
        "open_event_count": sum(not value for value in event_states.values()),
        "frontier_record_count": len(records),
        "observed_trigger_price_recoveries": sum(
            record["trigger_price_recovery"]["status"] == "observed"
            for record in records
        ),
        "censored_trigger_price_recoveries": sum(
            record["trigger_price_recovery"]["status"] == "censored"
            for record in records
        ),
        "observed_peak_recoveries": sum(
            record["peak_recovery"]["status"] == "observed" for record in records
        ),
        "censored_peak_recoveries": sum(
            record["peak_recovery"]["status"] == "censored" for record in records
        ),
    }


def _limitations() -> list[str]:
    return [
        "Frontier records are path facts, not buy signals or independent samples.",
        "A later threshold study must use at most one record per event per threshold.",
        "Observed does not imply future recovery; censored does not imply failure.",
        "Fixed horizons use trading sessions and can extend beyond event recovery.",
        "No probabilities, aggregate returns, thresholds, or strategy results "
        "are calculated.",
        "Historical decisions must use the point-in-time interface.",
    ]


def main() -> int:
    reports = build_drawdown_outcome_report_set(ROOT)
    target = ROOT / OUTPUT_RELATIVE
    publish_drawdown_outcome_report_set(target, reports)
    summary = reports["index.json"]["summary"]
    print(
        f"A-tier drawdown outcomes: analyzed={summary['analyzed_assets']} "
        f"blocked={summary['blocked_assets']} "
        f"records={summary['total_frontier_records']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
