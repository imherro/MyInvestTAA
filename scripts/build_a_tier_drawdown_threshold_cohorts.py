from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_taa.drawdown_outcomes import build_drawdown_outcomes
from current_taa.drawdown_profiles import build_drawdown_profile
from current_taa.drawdown_threshold_cohorts import (
    THRESHOLD_FAMILIES,
    build_threshold_cohorts,
)
from current_taa.research_universe import ResearchAsset, load_research_universe
from scripts.build_a_tier_drawdown_profiles import (
    AUDIT_RELATIVE,
    EVENT_INDEX_RELATIVE,
    _load_json,
    _replace_directory,
    _validate_event_file_set,
    _validate_event_identity,
    _validate_source_index,
)


OUTCOME_INDEX_RELATIVE = (
    "reports/strategy_research/drawdown_outcomes/index.json"
)
OUTPUT_RELATIVE = (
    "reports/strategy_research/drawdown_threshold_cohorts"
)


class DrawdownThresholdCohortBuildError(ValueError):
    pass


def build_drawdown_threshold_cohort_report_set(
    root: Path, *, generated_at: str | None = None
) -> dict[str, dict[str, Any]]:
    root = Path(root)
    universe = load_research_universe(root / "config/research_universe_v1.json")
    tier_a = universe.assets_for_tier("A")
    audit_bytes = (root / AUDIT_RELATIVE).read_bytes()
    event_index_bytes = (root / EVENT_INDEX_RELATIVE).read_bytes()
    outcome_index_bytes = (root / OUTCOME_INDEX_RELATIVE).read_bytes()
    audit = _load_json(audit_bytes, "universe audit")
    event_index = _load_json(event_index_bytes, "drawdown event index")
    outcome_index = _load_json(outcome_index_bytes, "drawdown outcome index")
    try:
        _validate_source_index(universe, tier_a, audit_bytes, audit, event_index)
        _validate_event_file_set(root, tier_a)
        _validate_outcome_file_set(root, tier_a)
        _validate_outcome_index(
            universe,
            tier_a,
            event_index_bytes,
            outcome_index,
        )
    except ValueError as exc:
        raise DrawdownThresholdCohortBuildError(str(exc)) from exc

    event_index_hash = hashlib.sha256(event_index_bytes).hexdigest()
    outcome_index_hash = hashlib.sha256(outcome_index_bytes).hexdigest()
    event_rows = {row["asset_key"]: row for row in event_index["assets"]}
    outcome_rows = {row["asset_key"]: row for row in outcome_index["assets"]}
    reports: dict[str, dict[str, Any]] = {}
    index_assets: list[dict[str, Any]] = []
    totals = {
        "analyzed": 0,
        "blocked": 0,
        "events": 0,
        "candidate_thresholds": 0,
        "reached": 0,
        "not_reached": 0,
        "insufficient_history": 0,
        "frontier_records": 0,
        "completed_events": 0,
        "open_events": 0,
    }

    for asset in tier_a:
        event_relative = (
            f"reports/strategy_research/drawdown_events/{asset.asset_key}.json"
        )
        outcome_relative = (
            f"reports/strategy_research/drawdown_outcomes/{asset.asset_key}.json"
        )
        if event_rows[asset.asset_key].get("report_path") != event_relative:
            raise DrawdownThresholdCohortBuildError(
                "event report path is not canonical"
            )
        if outcome_rows[asset.asset_key].get("report_path") != outcome_relative:
            raise DrawdownThresholdCohortBuildError(
                "outcome report path is not canonical"
            )
        event_bytes = (root / event_relative).read_bytes()
        outcome_bytes = (root / outcome_relative).read_bytes()
        event_report = _load_json(event_bytes, f"event report {asset.asset_key}")
        outcome_report = _load_json(
            outcome_bytes, f"outcome report {asset.asset_key}"
        )
        event_hash = hashlib.sha256(event_bytes).hexdigest()
        outcome_hash = hashlib.sha256(outcome_bytes).hexdigest()
        try:
            _validate_event_identity(
                asset,
                event_rows[asset.asset_key],
                event_report,
                universe.universe_hash,
                event_index,
            )
            _validate_outcome_report(
                asset,
                outcome_rows[asset.asset_key],
                event_report,
                event_relative,
                event_hash,
                outcome_report,
                outcome_index,
                event_index_hash,
            )
            if event_report["analysis_status"] == "analyzed":
                build_drawdown_profile(event_report)
            else:
                _validate_blocked_sources(event_report, outcome_report)
            expected_outcome = build_drawdown_outcomes(event_report)
            if any(
                outcome_report.get(field) != expected_outcome[field]
                for field in ("period", "summary", "records")
            ):
                raise DrawdownThresholdCohortBuildError(
                    "formal outcome business content differs from recomputation"
                )
            body = build_threshold_cohorts(event_report)
            _validate_cohort_body(body, event_report, outcome_report)
        except ValueError as exc:
            raise DrawdownThresholdCohortBuildError(str(exc)) from exc

        summary = body["summary"]
        status = event_report["analysis_status"]
        totals[status] += 1
        totals["events"] += summary["event_count"]
        totals["candidate_thresholds"] += summary["candidate_threshold_count"]
        totals["reached"] += summary["reached_count"]
        totals["not_reached"] += summary["not_reached_count"]
        totals["insufficient_history"] += summary["insufficient_history_count"]
        totals["frontier_records"] += outcome_report["summary"][
            "frontier_record_count"
        ]
        totals["completed_events"] += event_report["event_summary"][
            "completed_event_count"
        ]
        totals["open_events"] += event_report["event_summary"][
            "open_event_count"
        ]
        report = {
            "schema_version": "1.0",
            "report_type": "asset_drawdown_threshold_cohorts",
            "methodology_version": "1.0",
            "analysis_status": status,
            "asset": event_report["asset"],
            "universe_id": universe.universe_id,
            "universe_hash": universe.universe_hash,
            "source_event_index_path": EVENT_INDEX_RELATIVE,
            "source_event_index_sha256": event_index_hash,
            "source_event_report_path": event_relative,
            "source_event_report_sha256": event_hash,
            "source_outcome_index_path": OUTCOME_INDEX_RELATIVE,
            "source_outcome_index_sha256": outcome_index_hash,
            "source_outcome_report_path": outcome_relative,
            "source_outcome_report_sha256": outcome_hash,
            "period": body["period"],
            "summary": summary,
            "cohorts": body["cohorts"],
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
                "analysis_status": status,
                "report_path": f"{OUTPUT_RELATIVE}/{name}",
                **summary,
                "source_event_report_sha256": event_hash,
                "source_outcome_report_sha256": outcome_hash,
                "blockers": report["blockers"],
            }
        )

    _validate_source_summaries(event_index, outcome_index, totals)
    reports["index.json"] = {
        "schema_version": "1.0",
        "report_type": "a_tier_drawdown_threshold_cohort_index",
        "methodology_version": "1.0",
        "universe_id": universe.universe_id,
        "universe_hash": universe.universe_hash,
        "source_event_index_path": EVENT_INDEX_RELATIVE,
        "source_event_index_sha256": event_index_hash,
        "source_outcome_index_path": OUTCOME_INDEX_RELATIVE,
        "source_outcome_index_sha256": outcome_index_hash,
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "tier_a_assets": len(tier_a),
            "analyzed_assets": totals["analyzed"],
            "blocked_assets": totals["blocked"],
            "total_events": totals["events"],
            "total_candidate_thresholds": totals["candidate_thresholds"],
            "total_reached": totals["reached"],
            "total_not_reached": totals["not_reached"],
            "total_insufficient_history": totals["insufficient_history"],
        },
        "assets": index_assets,
        "limitations": _limitations(),
    }
    expected = {"index.json"} | {
        f"{asset.asset_key}.json" for asset in tier_a
    }
    if set(reports) != expected:
        raise DrawdownThresholdCohortBuildError(
            "cohort report set differs from tier A"
        )
    return reports


def publish_drawdown_threshold_cohort_report_set(
    target: Path, reports: dict[str, dict[str, Any]]
) -> None:
    target = Path(target)
    if len(reports) != 8 or "index.json" not in reports:
        raise DrawdownThresholdCohortBuildError(
            "cohort report set must contain eight files"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="cohort-stage-", dir=target.parent))
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


def _validate_outcome_file_set(
    root: Path, tier_a: tuple[ResearchAsset, ...]
) -> None:
    directory = root / Path(OUTCOME_INDEX_RELATIVE).parent
    expected = {"index.json"} | {
        f"{asset.asset_key}.json" for asset in tier_a
    }
    try:
        actual = {
            path.name
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() == ".json"
        }
    except OSError as exc:
        raise DrawdownThresholdCohortBuildError(
            "cannot inspect outcome source directory"
        ) from exc
    if actual != expected:
        raise DrawdownThresholdCohortBuildError(
            "outcome source directory must contain exactly the approved eight "
            "JSON files"
        )


def _validate_outcome_index(
    universe,
    tier_a: tuple[ResearchAsset, ...],
    event_index_bytes: bytes,
    outcome_index: dict[str, Any],
) -> None:
    if outcome_index.get("universe_id") != universe.universe_id or outcome_index.get(
        "universe_hash"
    ) != universe.universe_hash:
        raise DrawdownThresholdCohortBuildError(
            "outcome index does not match universe"
        )
    if (
        outcome_index.get("source_event_index_path") != EVENT_INDEX_RELATIVE
        or outcome_index.get("source_event_index_sha256")
        != hashlib.sha256(event_index_bytes).hexdigest()
    ):
        raise DrawdownThresholdCohortBuildError(
            "outcome index event source is stale"
        )
    rows = outcome_index.get("assets")
    expected = [asset.asset_key for asset in tier_a]
    if not isinstance(rows, list) or [row.get("asset_key") for row in rows] != expected:
        raise DrawdownThresholdCohortBuildError(
            "outcome index must contain tier A in order"
        )
    for asset, row in zip(tier_a, rows, strict=True):
        if (
            row.get("display_name") != asset.display_name
            or row.get("risk_family") != asset.risk_family
        ):
            raise DrawdownThresholdCohortBuildError(
                "outcome index identity differs from universe"
            )


def _validate_outcome_report(
    asset: ResearchAsset,
    outcome_row: dict[str, Any],
    event_report: dict[str, Any],
    event_relative: str,
    event_hash: str,
    outcome_report: dict[str, Any],
    outcome_index: dict[str, Any],
    event_index_hash: str,
) -> None:
    identity = outcome_report.get("asset", {})
    expected_identity = {
        "asset_key": asset.asset_key,
        "provider_code": asset.provider_code,
        "risk_family": asset.risk_family,
    }
    if any(identity.get(key) != value for key, value in expected_identity.items()):
        raise DrawdownThresholdCohortBuildError(
            "outcome report identity differs from universe"
        )
    if (
        outcome_report.get("analysis_status")
        != event_report.get("analysis_status")
        or outcome_row.get("analysis_status")
        != event_report.get("analysis_status")
    ):
        raise DrawdownThresholdCohortBuildError(
            "outcome analysis status differs from event source"
        )
    if (
        outcome_report.get("universe_id") != outcome_index.get("universe_id")
        or outcome_report.get("universe_hash")
        != outcome_index.get("universe_hash")
        or outcome_report.get("source_event_index_path") != EVENT_INDEX_RELATIVE
        or outcome_report.get("source_event_index_sha256") != event_index_hash
        or outcome_report.get("source_event_report_path") != event_relative
        or outcome_report.get("source_event_report_sha256") != event_hash
        or outcome_row.get("source_event_report_sha256") != event_hash
    ):
        raise DrawdownThresholdCohortBuildError(
            "outcome report source chain differs from current event source"
        )
    if outcome_report.get("blockers") != event_report.get("blockers"):
        raise DrawdownThresholdCohortBuildError(
            "outcome blockers differ from event source"
        )
    summary = outcome_report.get("summary", {})
    if (
        outcome_row.get("event_count") != summary.get("event_count")
        or outcome_row.get("frontier_record_count")
        != summary.get("frontier_record_count")
        or outcome_row.get("blockers") != outcome_report.get("blockers")
    ):
        raise DrawdownThresholdCohortBuildError(
            "outcome index row differs from outcome report"
        )


def _validate_blocked_sources(
    event_report: dict[str, Any], outcome_report: dict[str, Any]
) -> None:
    if event_report.get("events") != [] or event_report.get("drawdown_series") != []:
        raise DrawdownThresholdCohortBuildError(
            "blocked event report must have empty facts"
        )
    if event_report.get("current_state") is not None:
        raise DrawdownThresholdCohortBuildError(
            "blocked event report current state must be null"
        )
    if outcome_report.get("period") is not None or outcome_report.get("records") != []:
        raise DrawdownThresholdCohortBuildError(
            "blocked outcome report must have empty facts"
        )


def _validate_cohort_body(
    body: dict[str, Any],
    event_report: dict[str, Any],
    outcome_report: dict[str, Any],
) -> None:
    events = event_report.get("events", [])
    cohorts = body.get("cohorts")
    if not isinstance(cohorts, list) or len(cohorts) != len(events) * 15:
        raise DrawdownThresholdCohortBuildError(
            "each analyzed event must produce fifteen cohorts"
        )
    records_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in outcome_report.get("records", []):
        records_by_event[record["event_id"]].append(record)
    expected_order = []
    for event in events:
        for family, levels in THRESHOLD_FAMILIES:
            expected_order.extend(
                (event["event_sequence"], family, level) for level, _ in levels
            )
    actual_order = [
        (row["event_sequence"], row["threshold_family"], row["threshold_level"])
        for row in cohorts
    ]
    if actual_order != expected_order:
        raise DrawdownThresholdCohortBuildError("cohort order is not canonical")
    ids: set[str] = set()
    for row in cohorts:
        expected_id = (
            f"{row['asset_key']}:{row['event_sequence']}:"
            f"{row['threshold_family']}:{row['threshold_level']}"
        )
        if row.get("cohort_id") != expected_id or expected_id in ids:
            raise DrawdownThresholdCohortBuildError(
                "cohort IDs must be stable and unique"
            )
        ids.add(expected_id)
        threshold = row.get("threshold_depth")
        frontier = sorted(
            records_by_event.get(row["event_id"], []),
            key=lambda record: record["frontier_sequence"],
        )
        expected_selected = (
            next(
                (
                    record
                    for record in frontier
                    if record["trigger_depth"] >= threshold
                ),
                None,
            )
            if threshold is not None
            else None
        )
        _validate_crossing(row, expected_selected)
    if body.get("summary") != _summary_from_cohorts(events, cohorts):
        raise DrawdownThresholdCohortBuildError(
            "cohort summary differs from facts"
        )


def _validate_crossing(
    cohort: dict[str, Any], selected: dict[str, Any] | None
) -> None:
    status = cohort.get("threshold_status")
    if cohort.get("sample_count") == 0:
        if (
            status != "insufficient_history"
            or cohort.get("threshold_depth") is not None
        ):
            raise DrawdownThresholdCohortBuildError(
                "empty threshold sample has invalid status"
            )
    elif status == "insufficient_history" or cohort.get("threshold_depth") is None:
        raise DrawdownThresholdCohortBuildError(
            "non-empty threshold sample has invalid status"
        )
    if selected is None:
        expected_status = (
            "insufficient_history"
            if cohort.get("threshold_depth") is None
            else "not_reached"
        )
        if status != expected_status or any(
            cohort.get(field) is not None
            for field in (
                "selected_record_id",
                "selected_frontier_sequence",
                "trigger_date",
                "trigger_depth",
                "trigger_drawdown",
            )
        ):
            raise DrawdownThresholdCohortBuildError(
                "non-reached cohort has invalid selection"
            )
        return
    expected = {
        "selected_record_id": selected["record_id"],
        "selected_frontier_sequence": selected["frontier_sequence"],
        "trigger_date": selected["trigger_date"],
        "trigger_depth": selected["trigger_depth"],
        "trigger_drawdown": selected["trigger_drawdown"],
    }
    if status != "reached" or any(
        cohort.get(field) != value for field, value in expected.items()
    ):
        raise DrawdownThresholdCohortBuildError(
            "reached cohort is not the first threshold crossing"
        )


def _validate_source_summaries(
    event_index: dict[str, Any],
    outcome_index: dict[str, Any],
    totals: dict[str, int],
) -> None:
    expected_event = {
        "tier_a_assets": 7,
        "analyzed_assets": totals["analyzed"],
        "blocked_assets": totals["blocked"],
        "completed_events": totals["completed_events"],
        "open_events": totals["open_events"],
    }
    if event_index.get("summary") != expected_event:
        raise DrawdownThresholdCohortBuildError(
            "event index summary differs from asset reports"
        )
    expected_outcome = {
        "tier_a_assets": 7,
        "analyzed_assets": totals["analyzed"],
        "blocked_assets": totals["blocked"],
        "total_events": totals["events"],
        "total_frontier_records": totals["frontier_records"],
    }
    if outcome_index.get("summary") != expected_outcome:
        raise DrawdownThresholdCohortBuildError(
            "outcome index summary differs from asset reports"
        )


def _summary_from_cohorts(
    events: list[dict[str, Any]], cohorts: list[dict[str, Any]]
) -> dict[str, int]:
    return {
        "event_count": len(events),
        "candidate_threshold_count": len(cohorts),
        "reached_count": sum(
            row["threshold_status"] == "reached" for row in cohorts
        ),
        "not_reached_count": sum(
            row["threshold_status"] == "not_reached" for row in cohorts
        ),
        "insufficient_history_count": sum(
            row["threshold_status"] == "insufficient_history" for row in cohorts
        ),
    }


def _validate_stage(
    stage: Path, reports: dict[str, dict[str, Any]]
) -> None:
    if {path.name for path in stage.iterdir() if path.is_file()} != set(reports):
        raise DrawdownThresholdCohortBuildError(
            "staged cohort reports are incomplete"
        )
    loaded = {
        name: json.loads((stage / name).read_text(encoding="utf-8"))
        for name in reports
    }
    index = loaded["index.json"]
    totals = {
        "analyzed": 0,
        "blocked": 0,
        "events": 0,
        "candidate_thresholds": 0,
        "reached": 0,
        "not_reached": 0,
        "insufficient_history": 0,
    }
    for row in index["assets"]:
        report = loaded.get(Path(row["report_path"]).name)
        if report is None or report["asset"]["asset_key"] != row["asset_key"]:
            raise DrawdownThresholdCohortBuildError(
                "cohort index reference is invalid"
            )
        if (
            report["universe_hash"] != index["universe_hash"]
            or report["source_event_index_sha256"]
            != index["source_event_index_sha256"]
            or report["source_outcome_index_sha256"]
            != index["source_outcome_index_sha256"]
        ):
            raise DrawdownThresholdCohortBuildError(
                "cohort source chain differs from index"
            )
        summary_fields = (
            "event_count",
            "candidate_threshold_count",
            "reached_count",
            "not_reached_count",
            "insufficient_history_count",
        )
        if (
            any(
                row.get(field) != report["summary"].get(field)
                for field in summary_fields
            )
            or row.get("analysis_status") != report.get("analysis_status")
            or row.get("source_event_report_sha256")
            != report.get("source_event_report_sha256")
            or row.get("source_outcome_report_sha256")
            != report.get("source_outcome_report_sha256")
            or row.get("blockers") != report.get("blockers")
        ):
            raise DrawdownThresholdCohortBuildError(
                "cohort index row differs from asset report"
            )
        cohorts = report["cohorts"]
        event_ids = {cohort["event_id"] for cohort in cohorts}
        if report["analysis_status"] == "blocked":
            event_ids = set()
        event_facts = [
            {"event_id": event_id}
            for event_id in sorted(event_ids)
        ]
        expected_summary = _summary_from_cohorts(event_facts, cohorts)
        if report["summary"] != expected_summary:
            raise DrawdownThresholdCohortBuildError(
                "staged cohort summary differs from facts"
            )
        cohort_ids = [cohort["cohort_id"] for cohort in cohorts]
        if len(cohort_ids) != len(set(cohort_ids)):
            raise DrawdownThresholdCohortBuildError(
                "staged cohort IDs are not unique"
            )
        for cohort in cohorts:
            expected_id = (
                f"{cohort['asset_key']}:{cohort['event_sequence']}:"
                f"{cohort['threshold_family']}:{cohort['threshold_level']}"
            )
            if cohort["cohort_id"] != expected_id:
                raise DrawdownThresholdCohortBuildError(
                    "staged cohort ID is not canonical"
                )
        groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
        for cohort in cohorts:
            groups[(cohort["event_sequence"], cohort["event_id"])].append(cohort)
        if any(len(group) != 15 for group in groups.values()):
            raise DrawdownThresholdCohortBuildError(
                "staged event does not contain fifteen cohorts"
            )
        family_order = {
            family: index for index, (family, _) in enumerate(THRESHOLD_FAMILIES)
        }
        level_order = {
            (family, level): index
            for family, levels in THRESHOLD_FAMILIES
            for index, (level, _) in enumerate(levels)
        }
        actual_order = [
            (
                cohort["event_sequence"],
                family_order[cohort["threshold_family"]],
                level_order[(cohort["threshold_family"], cohort["threshold_level"])],
            )
            for cohort in cohorts
        ]
        if actual_order != sorted(actual_order):
            raise DrawdownThresholdCohortBuildError(
                "staged cohort order is not canonical"
            )
        summary = report["summary"]
        status = report["analysis_status"]
        totals[status] += 1
        for key in (
            "events",
            "candidate_thresholds",
            "reached",
            "not_reached",
            "insufficient_history",
        ):
            field = {
                "events": "event_count",
                "candidate_thresholds": "candidate_threshold_count",
                "reached": "reached_count",
                "not_reached": "not_reached_count",
                "insufficient_history": "insufficient_history_count",
            }[key]
            totals[key] += summary[field]
    expected_index_summary = {
        "tier_a_assets": 7,
        "analyzed_assets": totals["analyzed"],
        "blocked_assets": totals["blocked"],
        "total_events": totals["events"],
        "total_candidate_thresholds": totals["candidate_thresholds"],
        "total_reached": totals["reached"],
        "total_not_reached": totals["not_reached"],
        "total_insufficient_history": totals["insufficient_history"],
    }
    if index["summary"] != expected_index_summary:
        raise DrawdownThresholdCohortBuildError(
            "cohort index summary differs from reports"
        )


def _limitations() -> list[str]:
    return [
        "Thresholds are research candidates, not formal strategy parameters.",
        "Each event threshold is frozen at its peak date using only then-visible "
        "history.",
        "The current event is excluded from its own threshold estimation.",
        "Each event contributes at most one record to each candidate threshold.",
        "Threshold cohorts from the same event remain highly dependent.",
        "Small samples do not establish threshold reliability.",
        "No probabilities, return aggregates, positions, or strategy performance "
        "are calculated.",
        "Historical decisions must use the point-in-time interface.",
        "Full-history terminal quantiles or maximum drawdowns must not be used as "
        "historical thresholds.",
    ]


def main() -> int:
    reports = build_drawdown_threshold_cohort_report_set(ROOT)
    target = ROOT / OUTPUT_RELATIVE
    publish_drawdown_threshold_cohort_report_set(target, reports)
    summary = reports["index.json"]["summary"]
    print(
        f"A-tier drawdown threshold cohorts: "
        f"analyzed={summary['analyzed_assets']} "
        f"blocked={summary['blocked_assets']} "
        f"cohorts={summary['total_candidate_thresholds']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
