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
from current_taa.drawdown_threshold_statistics import (
    _kaplan_meier,
    build_threshold_statistics,
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
    build_drawdown_threshold_cohort_report_set,
)


COHORT_INDEX_RELATIVE = f"{COHORT_OUTPUT_RELATIVE}/index.json"
OUTPUT_RELATIVE = "reports/strategy_research/drawdown_threshold_statistics"


class DrawdownThresholdStatisticsBuildError(ValueError):
    pass


def build_drawdown_threshold_statistics_report_set(
    root: Path, *, generated_at: str | None = None
) -> dict[str, dict[str, Any]]:
    root = Path(root)
    universe = load_research_universe(root / "config/research_universe_v1.json")
    tier_a = universe.assets_for_tier("A")
    _validate_json_file_set(root, EVENT_INDEX_RELATIVE, tier_a, "event")
    _validate_json_file_set(root, OUTCOME_INDEX_RELATIVE, tier_a, "outcome")
    _validate_json_file_set(root, COHORT_INDEX_RELATIVE, tier_a, "cohort")

    event_index_bytes = (root / EVENT_INDEX_RELATIVE).read_bytes()
    outcome_index_bytes = (root / OUTCOME_INDEX_RELATIVE).read_bytes()
    cohort_index_bytes = (root / COHORT_INDEX_RELATIVE).read_bytes()
    cohort_index = _load_json(cohort_index_bytes, "drawdown cohort index")
    try:
        expected_cohorts = build_drawdown_threshold_cohort_report_set(
            root, generated_at=cohort_index.get("generated_at")
        )
    except ValueError as exc:
        raise DrawdownThresholdStatisticsBuildError(str(exc)) from exc
    formal_cohorts = _load_report_set(
        root, COHORT_OUTPUT_RELATIVE, expected_cohorts
    )
    if formal_cohorts != expected_cohorts:
        raise DrawdownThresholdStatisticsBuildError(
            "formal cohort business content differs from recomputation"
        )

    event_index_hash = hashlib.sha256(event_index_bytes).hexdigest()
    outcome_index_hash = hashlib.sha256(outcome_index_bytes).hexdigest()
    cohort_index_hash = hashlib.sha256(cohort_index_bytes).hexdigest()
    reports: dict[str, dict[str, Any]] = {}
    index_assets: list[dict[str, Any]] = []
    totals = {"analyzed": 0, "blocked": 0, "groups": 0, "reached": 0}

    for asset in tier_a:
        name = f"{asset.asset_key}.json"
        event_relative = (
            f"reports/strategy_research/drawdown_events/{name}"
        )
        outcome_relative = (
            f"reports/strategy_research/drawdown_outcomes/{name}"
        )
        cohort_relative = f"{COHORT_OUTPUT_RELATIVE}/{name}"
        event_bytes = (root / event_relative).read_bytes()
        outcome_bytes = (root / outcome_relative).read_bytes()
        cohort_bytes = (root / cohort_relative).read_bytes()
        event_report = _load_json(event_bytes, f"event report {asset.asset_key}")
        outcome_report = _load_json(
            outcome_bytes, f"outcome report {asset.asset_key}"
        )
        cohort_report = formal_cohorts[name]
        try:
            _validate_selected_links(asset, outcome_report, cohort_report)
            body = build_threshold_statistics(event_report)
            _validate_statistics_body(body, event_report["analysis_status"])
        except ValueError as exc:
            raise DrawdownThresholdStatisticsBuildError(str(exc)) from exc

        status = event_report["analysis_status"]
        summary = body["summary"]
        totals[status] += 1
        totals["groups"] += summary["threshold_group_count"]
        totals["reached"] += summary["total_reached_cohorts"]
        report = {
            "schema_version": "1.0",
            "report_type": "asset_drawdown_threshold_statistics",
            "methodology_version": "1.0",
            "analysis_status": status,
            "asset": event_report["asset"],
            "universe_id": universe.universe_id,
            "universe_hash": universe.universe_hash,
            "source_event_index_path": EVENT_INDEX_RELATIVE,
            "source_event_index_sha256": event_index_hash,
            "source_event_report_path": event_relative,
            "source_event_report_sha256": hashlib.sha256(event_bytes).hexdigest(),
            "source_outcome_index_path": OUTCOME_INDEX_RELATIVE,
            "source_outcome_index_sha256": outcome_index_hash,
            "source_outcome_report_path": outcome_relative,
            "source_outcome_report_sha256": hashlib.sha256(
                outcome_bytes
            ).hexdigest(),
            "source_cohort_index_path": COHORT_INDEX_RELATIVE,
            "source_cohort_index_sha256": cohort_index_hash,
            "source_cohort_report_path": cohort_relative,
            "source_cohort_report_sha256": hashlib.sha256(
                cohort_bytes
            ).hexdigest(),
            "period": body["period"],
            "summary": summary,
            "threshold_statistics": body["threshold_statistics"],
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
                "source_event_report_sha256": report[
                    "source_event_report_sha256"
                ],
                "source_outcome_report_sha256": report[
                    "source_outcome_report_sha256"
                ],
                "source_cohort_report_sha256": report[
                    "source_cohort_report_sha256"
                ],
                "blockers": report["blockers"],
            }
        )

    reports["index.json"] = {
        "schema_version": "1.0",
        "report_type": "a_tier_drawdown_threshold_statistics_index",
        "methodology_version": "1.0",
        "universe_id": universe.universe_id,
        "universe_hash": universe.universe_hash,
        "source_event_index_path": EVENT_INDEX_RELATIVE,
        "source_event_index_sha256": event_index_hash,
        "source_outcome_index_path": OUTCOME_INDEX_RELATIVE,
        "source_outcome_index_sha256": outcome_index_hash,
        "source_cohort_index_path": COHORT_INDEX_RELATIVE,
        "source_cohort_index_sha256": cohort_index_hash,
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "tier_a_assets": len(tier_a),
            "analyzed_assets": totals["analyzed"],
            "blocked_assets": totals["blocked"],
            "threshold_groups_per_analyzed_asset": 15,
            "total_threshold_groups": totals["groups"],
            "total_reached_cohorts": totals["reached"],
        },
        "assets": index_assets,
        "limitations": _limitations(),
    }
    expected_names = {"index.json"} | {
        f"{asset.asset_key}.json" for asset in tier_a
    }
    if set(reports) != expected_names:
        raise DrawdownThresholdStatisticsBuildError(
            "statistics report set differs from tier A"
        )
    return reports


def publish_drawdown_threshold_statistics_report_set(
    target: Path, reports: dict[str, dict[str, Any]]
) -> None:
    target = Path(target)
    if len(reports) != 8 or "index.json" not in reports:
        raise DrawdownThresholdStatisticsBuildError(
            "statistics report set must contain eight files"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="statistics-stage-", dir=target.parent))
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


def _validate_json_file_set(
    root: Path,
    index_relative: str,
    tier_a: tuple[ResearchAsset, ...],
    description: str,
) -> None:
    directory = root / Path(index_relative).parent
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
        raise DrawdownThresholdStatisticsBuildError(
            f"cannot inspect {description} source directory"
        ) from exc
    if actual != expected:
        raise DrawdownThresholdStatisticsBuildError(
            f"{description} source directory must contain exactly the approved "
            "eight JSON files"
        )


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


def _validate_selected_links(
    asset: ResearchAsset,
    outcome_report: dict[str, Any],
    cohort_report: dict[str, Any],
) -> None:
    if (
        outcome_report.get("analysis_status")
        != cohort_report.get("analysis_status")
        or outcome_report.get("asset") != cohort_report.get("asset")
        or outcome_report.get("asset", {}).get("asset_key") != asset.asset_key
    ):
        raise DrawdownThresholdStatisticsBuildError(
            "outcome and cohort identities differ"
        )
    records: dict[str, list[dict[str, Any]]] = {}
    for record in outcome_report.get("records", []):
        records.setdefault(record["record_id"], []).append(record)
    for cohort in cohort_report.get("cohorts", []):
        if cohort.get("threshold_status") != "reached":
            continue
        matches = records.get(cohort.get("selected_record_id"), [])
        if len(matches) != 1:
            raise DrawdownThresholdStatisticsBuildError(
                "selected_record_id must identify exactly one outcome record"
            )
        record = matches[0]
        fields = {
            "event_id": "event_id",
            "event_sequence": "event_sequence",
            "selected_frontier_sequence": "frontier_sequence",
            "trigger_date": "trigger_date",
            "trigger_depth": "trigger_depth",
            "trigger_drawdown": "trigger_drawdown",
        }
        if cohort.get("asset_key") != record.get("asset_key") or any(
            cohort.get(cohort_field) != record.get(record_field)
            for cohort_field, record_field in fields.items()
        ):
            raise DrawdownThresholdStatisticsBuildError(
                "cohort trigger identity differs from selected outcome"
            )


def _validate_statistics_body(body: dict[str, Any], status: str) -> None:
    statistics = body.get("threshold_statistics")
    summary = body.get("summary")
    if not isinstance(statistics, list) or not isinstance(summary, dict):
        raise DrawdownThresholdStatisticsBuildError(
            "statistics body is invalid"
        )
    if status == "blocked":
        if body.get("period") is not None or statistics != [] or summary != {
            "threshold_group_count": 0,
            "total_event_count": 0,
            "total_reached_cohorts": 0,
        }:
            raise DrawdownThresholdStatisticsBuildError(
                "blocked statistics must contain empty facts"
            )
        return
    expected_order = [
        (family, level)
        for family, levels in THRESHOLD_FAMILIES
        for level, _ in levels
    ]
    actual_order = [
        (row.get("threshold_family"), row.get("threshold_level"))
        for row in statistics
    ]
    if actual_order != expected_order or len(set(actual_order)) != 15:
        raise DrawdownThresholdStatisticsBuildError(
            "statistics threshold order is invalid"
        )
    for row in statistics:
        _validate_coverage(row["coverage"])
        _validate_km(row["trigger_price_recovery"])
        _validate_km(row["peak_recovery"])
        _validate_minimum(row["minimum_outcome"])
        _validate_horizons(row["horizon_outcomes"])
        reached = row["coverage"]["reached_event_count"]
        if (
            row["trigger_price_recovery"]["sample_count"] != reached
            or row["peak_recovery"]["sample_count"] != reached
            or row["minimum_outcome"]["realized_count"]
            + row["minimum_outcome"]["censored_count"]
            != reached
            or any(
                horizon["observed_window_count"]
                + horizon["censored_window_count"]
                != reached
                for horizon in row["horizon_outcomes"]
            )
        ):
            raise DrawdownThresholdStatisticsBuildError(
                "threshold outcome sample counts differ from reached cohorts"
            )
    event_counts = {
        row["coverage"]["total_event_count"] for row in statistics
    }
    if len(event_counts) != 1:
        raise DrawdownThresholdStatisticsBuildError(
            "threshold groups do not cover the same event set"
        )
    expected_summary = {
        "threshold_group_count": 15,
        "total_event_count": (
            statistics[0]["coverage"]["total_event_count"]
            if statistics
            else 0
        ),
        "total_reached_cohorts": sum(
            row["coverage"]["reached_event_count"] for row in statistics
        ),
    }
    if summary != expected_summary:
        raise DrawdownThresholdStatisticsBuildError(
            "statistics summary differs from threshold rows"
        )
    _validate_finite(body)


def _validate_coverage(coverage: dict[str, Any]) -> None:
    insufficient = coverage["insufficient_history_count"]
    available = coverage["threshold_available_event_count"]
    reached = coverage["reached_event_count"]
    not_reached = coverage["not_reached_event_count"]
    if (
        coverage["total_event_count"] != insufficient + available
        or available != reached + not_reached
    ):
        raise DrawdownThresholdStatisticsBuildError(
            "threshold coverage is inconsistent"
        )
    expected_rate = round(reached / available, 10) if available else None
    if coverage["attainment_rate"] != expected_rate:
        raise DrawdownThresholdStatisticsBuildError(
            "threshold attainment rate is inconsistent"
        )


def _validate_km(km: dict[str, Any]) -> None:
    if km != _kaplan_meier(km.get("samples", [])):
        raise DrawdownThresholdStatisticsBuildError(
            "KM estimate differs from recovery samples"
        )
    if km["sample_count"] != km["observed_count"] + km["censored_count"]:
        raise DrawdownThresholdStatisticsBuildError(
            "KM sample counts are inconsistent"
        )
    if len(km["samples"]) != km["sample_count"]:
        raise DrawdownThresholdStatisticsBuildError(
            "KM samples differ from summary"
        )
    previous_survival = 1.0
    previous_recovery = 0.0
    previous_time = -1
    for row in km["timeline"]:
        survival = row["survival_probability"]
        recovery = row["recovery_probability"]
        if (
            row["time_sessions"] <= previous_time
            or not 0 <= survival <= previous_survival <= 1
            or not 0 <= previous_recovery <= recovery <= 1
            or round(survival + recovery, 10) != 1.0
            or row["greenwood_standard_error"] < 0
        ):
            raise DrawdownThresholdStatisticsBuildError(
                "KM timeline is invalid"
            )
        previous_time = row["time_sessions"]
        previous_survival = survival
        previous_recovery = recovery
    if len(km["fixed_horizons"]) != 5:
        raise DrawdownThresholdStatisticsBuildError(
            "KM fixed horizon set is invalid"
        )
    for horizon in km["fixed_horizons"]:
        for field in (
            "survival_probability",
            "recovery_probability",
        ):
            value = horizon[field]
            if value is not None and not 0 <= value <= 1:
                raise DrawdownThresholdStatisticsBuildError(
                    "KM horizon probability is invalid"
                )


def _validate_minimum(minimum: dict[str, Any]) -> None:
    if minimum["additional_return_distribution"]["sample_count"] != minimum[
        "realized_count"
    ] or minimum["sessions_to_minimum_distribution"]["sample_count"] != minimum[
        "realized_count"
    ]:
        raise DrawdownThresholdStatisticsBuildError(
            "minimum outcome distribution counts are inconsistent"
        )


def _validate_horizons(horizons: list[dict[str, Any]]) -> None:
    if len(horizons) != 5:
        raise DrawdownThresholdStatisticsBuildError(
            "fixed outcome horizon set is invalid"
        )
    for horizon in horizons:
        observed = horizon["observed_window_count"]
        for field in (
            "forward_return_distribution",
            "maximum_adverse_excursion_distribution",
            "maximum_favorable_excursion_distribution",
        ):
            if horizon[field]["sample_count"] != observed:
                raise DrawdownThresholdStatisticsBuildError(
                    "fixed-window distribution count is inconsistent"
                )


def _validate_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise DrawdownThresholdStatisticsBuildError(
            "statistics output must contain only finite numbers"
        )
    if isinstance(value, dict):
        for nested in value.values():
            _validate_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _validate_finite(nested)


def _validate_stage(
    stage: Path, reports: dict[str, dict[str, Any]]
) -> None:
    if {path.name for path in stage.iterdir() if path.is_file()} != set(reports):
        raise DrawdownThresholdStatisticsBuildError(
            "staged statistics reports are incomplete"
        )
    loaded = {
        name: json.loads((stage / name).read_text(encoding="utf-8"))
        for name in reports
    }
    index = loaded["index.json"]
    totals = {"analyzed": 0, "blocked": 0, "groups": 0, "reached": 0}
    for row in index["assets"]:
        report = loaded.get(Path(row["report_path"]).name)
        if report is None or report["asset"]["asset_key"] != row["asset_key"]:
            raise DrawdownThresholdStatisticsBuildError(
                "statistics index reference is invalid"
            )
        for source in ("event", "outcome", "cohort"):
            if report[f"source_{source}_index_sha256"] != index[
                f"source_{source}_index_sha256"
            ]:
                raise DrawdownThresholdStatisticsBuildError(
                    "statistics source chain differs from index"
                )
            if row[f"source_{source}_report_sha256"] != report[
                f"source_{source}_report_sha256"
            ]:
                raise DrawdownThresholdStatisticsBuildError(
                    "statistics source report hash differs from index row"
                )
        _validate_statistics_body(
            {
                "period": report["period"],
                "summary": report["summary"],
                "threshold_statistics": report["threshold_statistics"],
            },
            report["analysis_status"],
        )
        if any(
            row.get(field) != report["summary"].get(field)
            for field in (
                "threshold_group_count",
                "total_event_count",
                "total_reached_cohorts",
            )
        ):
            raise DrawdownThresholdStatisticsBuildError(
                "statistics index row differs from asset report"
            )
        if (
            row.get("analysis_status") != report.get("analysis_status")
            or row.get("blockers") != report.get("blockers")
        ):
            raise DrawdownThresholdStatisticsBuildError(
                "statistics index status differs from asset report"
            )
        status = report["analysis_status"]
        totals[status] += 1
        totals["groups"] += report["summary"]["threshold_group_count"]
        totals["reached"] += report["summary"]["total_reached_cohorts"]
    expected_summary = {
        "tier_a_assets": 7,
        "analyzed_assets": totals["analyzed"],
        "blocked_assets": totals["blocked"],
        "threshold_groups_per_analyzed_asset": 15,
        "total_threshold_groups": totals["groups"],
        "total_reached_cohorts": totals["reached"],
    }
    if index["summary"] != expected_summary:
        raise DrawdownThresholdStatisticsBuildError(
            "statistics index summary differs from reports"
        )
    _validate_finite(loaded)


def _limitations() -> list[str]:
    return [
        "Candidate thresholds are not formal strategy parameters.",
        "Statistics remain within one asset, threshold family, and threshold level.",
        "Different thresholds from the same event remain highly dependent.",
        "Kaplan-Meier estimates assume non-informative censoring, which is unproven.",
        "Small-sample estimates are unstable.",
        "Naive observed fractions do not adjust for censoring and cannot replace "
        "KM estimates.",
        "Not-reached and insufficient-history events are not recovery failures.",
        "Observed fixed-window returns exclude incomplete windows.",
        "Realized minimum distributions exclude open-event censored minima and "
        "remain censoring-biased.",
        "No cross-asset pooling, threshold ranking, parameter selection, positions, "
        "or strategy returns are produced.",
        "Historical decisions must use the point-in-time interface.",
    ]


def main() -> int:
    reports = build_drawdown_threshold_statistics_report_set(ROOT)
    target = ROOT / OUTPUT_RELATIVE
    publish_drawdown_threshold_statistics_report_set(target, reports)
    summary = reports["index.json"]["summary"]
    print(
        f"A-tier drawdown threshold statistics: "
        f"analyzed={summary['analyzed_assets']} "
        f"blocked={summary['blocked_assets']} "
        f"groups={summary['total_threshold_groups']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
