from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_taa.drawdown_threshold_cohorts import THRESHOLD_FAMILIES
from current_taa.drawdown_walk_forward_evidence import (
    build_walk_forward_evidence,
)
from current_taa.research_universe import ResearchAsset, load_research_universe
from scripts.build_a_tier_drawdown_profiles import (
    EVENT_INDEX_RELATIVE,
    _load_json,
    _replace_directory,
)
from scripts.build_a_tier_drawdown_threshold_cohorts import (
    OUTCOME_INDEX_RELATIVE,
    OUTPUT_RELATIVE as COHORT_OUTPUT_RELATIVE,
)
from scripts.build_a_tier_drawdown_threshold_statistics import (
    OUTPUT_RELATIVE as STATISTICS_OUTPUT_RELATIVE,
    _validate_json_file_set,
    build_drawdown_threshold_statistics_report_set,
)


COHORT_INDEX_RELATIVE = f"{COHORT_OUTPUT_RELATIVE}/index.json"
STATISTICS_INDEX_RELATIVE = f"{STATISTICS_OUTPUT_RELATIVE}/index.json"
OUTPUT_RELATIVE = "reports/strategy_research/drawdown_walk_forward_evidence"


class DrawdownWalkForwardEvidenceBuildError(ValueError):
    pass


def build_drawdown_walk_forward_evidence_report_set(
    root: Path, *, generated_at: str | None = None
) -> dict[str, dict[str, Any]]:
    root = Path(root)
    universe = load_research_universe(root / "config/research_universe_v1.json")
    tier_a = universe.assets_for_tier("A")
    for relative, description in (
        (EVENT_INDEX_RELATIVE, "event"),
        (OUTCOME_INDEX_RELATIVE, "outcome"),
        (COHORT_INDEX_RELATIVE, "cohort"),
        (STATISTICS_INDEX_RELATIVE, "statistics"),
    ):
        try:
            _validate_json_file_set(root, relative, tier_a, description)
        except ValueError as exc:
            raise DrawdownWalkForwardEvidenceBuildError(str(exc)) from exc

    index_bytes = {
        "event": (root / EVENT_INDEX_RELATIVE).read_bytes(),
        "outcome": (root / OUTCOME_INDEX_RELATIVE).read_bytes(),
        "cohort": (root / COHORT_INDEX_RELATIVE).read_bytes(),
        "statistics": (root / STATISTICS_INDEX_RELATIVE).read_bytes(),
    }
    statistics_index = _load_json(
        index_bytes["statistics"], "drawdown threshold statistics index"
    )
    try:
        expected_statistics = build_drawdown_threshold_statistics_report_set(
            root, generated_at=statistics_index.get("generated_at")
        )
    except ValueError as exc:
        raise DrawdownWalkForwardEvidenceBuildError(str(exc)) from exc
    formal_statistics = _load_report_set(
        root, STATISTICS_OUTPUT_RELATIVE, expected_statistics
    )
    if formal_statistics != expected_statistics:
        raise DrawdownWalkForwardEvidenceBuildError(
            "formal statistics business content differs from recomputation"
        )

    index_hashes = {
        key: hashlib.sha256(value).hexdigest()
        for key, value in index_bytes.items()
    }
    reports: dict[str, dict[str, Any]] = {}
    index_assets: list[dict[str, Any]] = []
    totals = {
        "analyzed": 0,
        "blocked": 0,
        "events": 0,
        "snapshots": 0,
        "evaluations": 0,
    }

    for asset in tier_a:
        name = f"{asset.asset_key}.json"
        relatives = {
            "event": f"reports/strategy_research/drawdown_events/{name}",
            "outcome": f"reports/strategy_research/drawdown_outcomes/{name}",
            "cohort": f"{COHORT_OUTPUT_RELATIVE}/{name}",
            "statistics": f"{STATISTICS_OUTPUT_RELATIVE}/{name}",
        }
        source_bytes = {
            key: (root / relative).read_bytes()
            for key, relative in relatives.items()
        }
        event_report = _load_json(
            source_bytes["event"], f"event report {asset.asset_key}"
        )
        outcome_report = _load_json(
            source_bytes["outcome"], f"outcome report {asset.asset_key}"
        )
        cohort_report = _load_json(
            source_bytes["cohort"], f"cohort report {asset.asset_key}"
        )
        statistics_report = formal_statistics[name]
        try:
            _validate_source_identity(
                asset,
                event_report,
                outcome_report,
                cohort_report,
                statistics_report,
            )
            body = build_walk_forward_evidence(event_report)
            _validate_ledger_body(body, event_report["analysis_status"])
            _validate_ledger_links(body, cohort_report, outcome_report)
        except ValueError as exc:
            raise DrawdownWalkForwardEvidenceBuildError(str(exc)) from exc

        status = event_report["analysis_status"]
        summary = body["summary"]
        totals[status] += 1
        totals["events"] += summary["event_count"]
        totals["snapshots"] += summary["training_snapshot_count"]
        totals["evaluations"] += summary["threshold_evaluation_count"]
        report = {
            "schema_version": "1.0",
            "report_type": "asset_drawdown_walk_forward_evidence",
            "methodology_version": "1.0",
            "analysis_status": status,
            "asset": event_report["asset"],
            "universe_id": universe.universe_id,
            "universe_hash": universe.universe_hash,
            **_source_fields(relatives, source_bytes, index_hashes),
            "period": body["period"],
            "summary": summary,
            "event_evaluations": body["event_evaluations"],
            "blockers": list(event_report.get("blockers", [])),
            "limitations": _limitations(),
        }
        reports[name] = report
        index_assets.append(
            {
                "asset_key": asset.asset_key,
                "display_name": asset.display_name,
                "risk_family": asset.risk_family,
                "analysis_status": status,
                "report_path": f"{OUTPUT_RELATIVE}/{name}",
                **summary,
                **{
                    f"source_{key}_report_sha256": report[
                        f"source_{key}_report_sha256"
                    ]
                    for key in relatives
                },
                "blockers": report["blockers"],
            }
        )

    reports["index.json"] = {
        "schema_version": "1.0",
        "report_type": "a_tier_drawdown_walk_forward_evidence_index",
        "methodology_version": "1.0",
        "universe_id": universe.universe_id,
        "universe_hash": universe.universe_hash,
        **{
            f"source_{key}_index_path": relative
            for key, relative in (
                ("event", EVENT_INDEX_RELATIVE),
                ("outcome", OUTCOME_INDEX_RELATIVE),
                ("cohort", COHORT_INDEX_RELATIVE),
                ("statistics", STATISTICS_INDEX_RELATIVE),
            )
        },
        **{
            f"source_{key}_index_sha256": value
            for key, value in index_hashes.items()
        },
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "tier_a_assets": len(tier_a),
            "analyzed_assets": totals["analyzed"],
            "blocked_assets": totals["blocked"],
            "total_events": totals["events"],
            "total_training_snapshots": totals["snapshots"],
            "total_threshold_evaluations": totals["evaluations"],
        },
        "assets": index_assets,
        "limitations": _limitations(),
    }
    expected_names = {"index.json"} | {
        f"{asset.asset_key}.json" for asset in tier_a
    }
    if set(reports) != expected_names:
        raise DrawdownWalkForwardEvidenceBuildError(
            "walk-forward report set differs from tier A"
        )
    return reports


def publish_drawdown_walk_forward_evidence_report_set(
    target: Path, reports: dict[str, dict[str, Any]]
) -> None:
    target = Path(target)
    if len(reports) != 8 or "index.json" not in reports:
        raise DrawdownWalkForwardEvidenceBuildError(
            "walk-forward report set must contain eight files"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="walk-forward-stage-", dir=target.parent))
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


def _load_report_set(
    root: Path,
    relative_directory: str,
    expected: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        name: _load_json(
            (root / relative_directory / name).read_bytes(),
            f"formal report {name}",
        )
        for name in expected
    }


def _source_fields(
    relatives: dict[str, str],
    source_bytes: dict[str, bytes],
    index_hashes: dict[str, str],
) -> dict[str, str]:
    result = {}
    for key, relative in relatives.items():
        result[f"source_{key}_index_path"] = {
            "event": EVENT_INDEX_RELATIVE,
            "outcome": OUTCOME_INDEX_RELATIVE,
            "cohort": COHORT_INDEX_RELATIVE,
            "statistics": STATISTICS_INDEX_RELATIVE,
        }[key]
        result[f"source_{key}_index_sha256"] = index_hashes[key]
        result[f"source_{key}_report_path"] = relative
        result[f"source_{key}_report_sha256"] = hashlib.sha256(
            source_bytes[key]
        ).hexdigest()
    return result


def _validate_source_identity(
    asset: ResearchAsset,
    event_report: dict[str, Any],
    outcome_report: dict[str, Any],
    cohort_report: dict[str, Any],
    statistics_report: dict[str, Any],
) -> None:
    reports = (event_report, outcome_report, cohort_report, statistics_report)
    expected = {
        "asset_key": asset.asset_key,
        "provider_code": asset.provider_code,
        "risk_family": asset.risk_family,
    }
    if any(
        any(
            report.get("asset", {}).get(key) != value
            for key, value in expected.items()
        )
        for report in reports
    ):
        raise DrawdownWalkForwardEvidenceBuildError(
            "source report identity differs from universe"
        )
    statuses = {report.get("analysis_status") for report in reports}
    if len(statuses) != 1:
        raise DrawdownWalkForwardEvidenceBuildError(
            "source analysis statuses differ"
        )
    if event_report["analysis_status"] == "blocked" and any(
        (
            event_report.get("events") != [],
            event_report.get("drawdown_series") != [],
            outcome_report.get("records") != [],
            cohort_report.get("cohorts") != [],
            statistics_report.get("threshold_statistics") != [],
        )
    ):
        raise DrawdownWalkForwardEvidenceBuildError(
            "blocked source reports must contain empty facts"
        )


def _validate_ledger_links(
    body: dict[str, Any],
    cohort_report: dict[str, Any],
    outcome_report: dict[str, Any],
) -> None:
    formal_cohorts = {
        row["cohort_id"]: row for row in cohort_report.get("cohorts", [])
    }
    outcome_records: dict[str, list[dict[str, Any]]] = {}
    for record in outcome_report.get("records", []):
        outcome_records.setdefault(record["record_id"], []).append(record)
    cohort_fields = (
        "cohort_id",
        "threshold_status",
        "threshold_depth",
        "sample_count",
        "sample_start_date",
        "sample_end_date",
        "selected_record_id",
        "selected_frontier_sequence",
        "trigger_date",
        "trigger_depth",
        "trigger_drawdown",
    )
    outcome_fields = (
        "record_id",
        "event_id",
        "event_sequence",
        "frontier_sequence",
        "trigger_date",
        "trigger_close",
        "trigger_depth",
        "minimum_outcome",
        "trigger_price_recovery",
        "peak_recovery",
        "horizons",
    )
    for event in body["event_evaluations"]:
        for evaluation in event["threshold_evaluations"]:
            test_cohort = evaluation["test_cohort"]
            formal = formal_cohorts.get(test_cohort["cohort_id"])
            if formal is None or any(
                test_cohort[field] != formal[field] for field in cohort_fields
            ):
                raise DrawdownWalkForwardEvidenceBuildError(
                    "test cohort differs from formal cohort"
                )
            test_outcome = evaluation["test_outcome"]
            selected_id = test_cohort["selected_record_id"]
            if test_outcome is None:
                if selected_id is not None:
                    raise DrawdownWalkForwardEvidenceBuildError(
                        "null test outcome has a selected record"
                    )
                continue
            matches = outcome_records.get(selected_id, [])
            if len(matches) != 1 or any(
                test_outcome[field] != matches[0][field]
                for field in outcome_fields
            ):
                raise DrawdownWalkForwardEvidenceBuildError(
                    "test outcome differs from formal outcome"
                )


def _validate_ledger_body(body: dict[str, Any], status: str) -> None:
    events = body.get("event_evaluations")
    if not isinstance(events, list):
        raise DrawdownWalkForwardEvidenceBuildError(
            "walk-forward event evaluations must be a list"
        )
    if status == "blocked":
        if body.get("period") is not None or events != [] or body.get(
            "summary"
        ) != _empty_summary():
            raise DrawdownWalkForwardEvidenceBuildError(
                "blocked walk-forward report must be empty"
            )
        return
    expected_order = [
        (family, level)
        for family, levels in THRESHOLD_FAMILIES
        for level, _ in levels
    ]
    states = {"reached": 0, "not_reached": 0, "insufficient_history": 0}
    for sequence, event in enumerate(events, start=1):
        snapshot = event["training_snapshot"]
        if (
            event["event_sequence"] != sequence
            or snapshot["prior_event_count"] != sequence - 1
            or snapshot["training_cutoff_date"] != event["peak_date"]
            or snapshot["training_snapshot_id"]
            != f"{event['event_id'].split(':')[0]}:{sequence}:{event['peak_date']}"
            or snapshot["threshold_group_count"] != 15
        ):
            raise DrawdownWalkForwardEvidenceBuildError(
                "training snapshot identity or isolation is invalid"
            )
        training = snapshot["threshold_statistics"]
        evaluations = event["threshold_evaluations"]
        training_order = [
            (row["threshold_family"], row["threshold_level"])
            for row in training
        ]
        evaluation_order = [
            (row["threshold_family"], row["threshold_level"])
            for row in evaluations
        ]
        if training_order != expected_order or evaluation_order != expected_order:
            raise DrawdownWalkForwardEvidenceBuildError(
                "walk-forward threshold order is invalid"
            )
        for training_group, evaluation in zip(
            training, evaluations, strict=True
        ):
            group_hash = training_group["training_group_sha256"]
            if (
                len(group_hash) != 64
                or any(character not in "0123456789abcdef" for character in group_hash)
                or evaluation["training_group_sha256"] != group_hash
                or training_group["coverage"]["total_event_count"] != sequence - 1
            ):
                raise DrawdownWalkForwardEvidenceBuildError(
                    "training group hash or coverage is invalid"
                )
            expected_id = (
                f"{event['event_id'].split(':')[0]}:{sequence}:"
                f"{evaluation['threshold_family']}:"
                f"{evaluation['threshold_level']}"
            )
            if evaluation["evaluation_id"] != expected_id:
                raise DrawdownWalkForwardEvidenceBuildError(
                    "threshold evaluation ID is invalid"
                )
            state = evaluation["test_cohort"]["threshold_status"]
            if state not in states:
                raise DrawdownWalkForwardEvidenceBuildError(
                    "threshold evaluation status is invalid"
                )
            states[state] += 1
            if (state == "reached") != (evaluation["test_outcome"] is not None):
                raise DrawdownWalkForwardEvidenceBuildError(
                    "threshold evaluation outcome state is invalid"
                )
    expected_summary = {
        "event_count": len(events),
        "training_snapshot_count": len(events),
        "threshold_evaluation_count": len(events) * 15,
        "reached_count": states["reached"],
        "not_reached_count": states["not_reached"],
        "insufficient_history_count": states["insufficient_history"],
    }
    if body.get("summary") != expected_summary:
        raise DrawdownWalkForwardEvidenceBuildError(
            "walk-forward summary differs from evaluations"
        )
    _validate_finite(body)


def _empty_summary() -> dict[str, int]:
    return {
        "event_count": 0,
        "training_snapshot_count": 0,
        "threshold_evaluation_count": 0,
        "reached_count": 0,
        "not_reached_count": 0,
        "insufficient_history_count": 0,
    }


def _validate_stage(
    stage: Path, reports: dict[str, dict[str, Any]]
) -> None:
    if {path.name for path in stage.iterdir() if path.is_file()} != set(reports):
        raise DrawdownWalkForwardEvidenceBuildError(
            "staged walk-forward reports are incomplete"
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
        "snapshots": 0,
        "evaluations": 0,
    }
    for row in index["assets"]:
        report = loaded.get(Path(row["report_path"]).name)
        if report is None or report["asset"]["asset_key"] != row["asset_key"]:
            raise DrawdownWalkForwardEvidenceBuildError(
                "walk-forward index reference is invalid"
            )
        for source in ("event", "outcome", "cohort", "statistics"):
            if report[f"source_{source}_index_sha256"] != index[
                f"source_{source}_index_sha256"
            ] or report[f"source_{source}_report_sha256"] != row[
                f"source_{source}_report_sha256"
            ]:
                raise DrawdownWalkForwardEvidenceBuildError(
                    "walk-forward source chain differs from index"
                )
        _validate_ledger_body(
            {
                "period": report["period"],
                "summary": report["summary"],
                "event_evaluations": report["event_evaluations"],
            },
            report["analysis_status"],
        )
        if (
            row["analysis_status"] != report["analysis_status"]
            or row["blockers"] != report["blockers"]
            or any(
                row.get(field) != report["summary"].get(field)
                for field in _empty_summary()
            )
        ):
            raise DrawdownWalkForwardEvidenceBuildError(
                "walk-forward index row differs from asset report"
            )
        status = report["analysis_status"]
        totals[status] += 1
        totals["events"] += report["summary"]["event_count"]
        totals["snapshots"] += report["summary"]["training_snapshot_count"]
        totals["evaluations"] += report["summary"][
            "threshold_evaluation_count"
        ]
    expected_summary = {
        "tier_a_assets": 7,
        "analyzed_assets": totals["analyzed"],
        "blocked_assets": totals["blocked"],
        "total_events": totals["events"],
        "total_training_snapshots": totals["snapshots"],
        "total_threshold_evaluations": totals["evaluations"],
    }
    if index["summary"] != expected_summary:
        raise DrawdownWalkForwardEvidenceBuildError(
            "walk-forward index summary differs from reports"
        )
    _validate_finite(loaded)


def _validate_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise DrawdownWalkForwardEvidenceBuildError(
            "walk-forward output must contain only finite numbers"
        )
    if isinstance(value, dict):
        for nested in value.values():
            _validate_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _validate_finite(nested)


def _limitations() -> list[str]:
    return [
        "This is expanding walk-forward evidence, not a strategy.",
        "Each event training cutoff is its own peak date.",
        "The current event is excluded from its own training statistics.",
        "Current-event evaluation can remain right-censored.",
        "The fifteen threshold evaluations within one event are highly dependent.",
        "Repeated events for one threshold are not guaranteed to be independent "
        "or identically distributed.",
        "Small training samples can be extremely unstable.",
        "No threshold scoring, ranking, selection, positions, trade instructions, "
        "or strategy returns are produced.",
        "Future parameter research must use this walk-forward evidence rather than "
        "full-history terminal statistics.",
    ]


def main() -> int:
    reports = build_drawdown_walk_forward_evidence_report_set(ROOT)
    target = ROOT / OUTPUT_RELATIVE
    publish_drawdown_walk_forward_evidence_report_set(target, reports)
    summary = reports["index.json"]["summary"]
    print(
        f"A-tier walk-forward evidence: analyzed={summary['analyzed_assets']} "
        f"blocked={summary['blocked_assets']} "
        f"evaluations={summary['total_threshold_evaluations']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
