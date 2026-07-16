from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

from current_taa.drawdown_events import analyze_drawdown_history
from current_taa.drawdown_outcomes import build_drawdown_outcomes
from current_taa.drawdown_profiles import build_drawdown_profile
from current_taa.drawdown_threshold_cohorts import (
    THRESHOLD_FAMILIES,
    build_threshold_cohorts,
)
from current_taa.drawdown_threshold_statistics import build_threshold_statistics


class DrawdownWalkForwardEvidenceError(ValueError):
    pass


def build_walk_forward_evidence(
    asset_event_report: dict[str, Any], *, as_of_date: str | None = None
) -> dict[str, Any]:
    if not isinstance(asset_event_report, dict):
        raise DrawdownWalkForwardEvidenceError(
            "asset event report must be an object"
        )
    status = asset_event_report.get("analysis_status")
    if status == "blocked":
        return {
            "period": None,
            "summary": _summary([]),
            "event_evaluations": [],
        }
    if status != "analyzed":
        raise DrawdownWalkForwardEvidenceError(
            "asset event report must be analyzed or blocked"
        )
    asset = asset_event_report.get("asset")
    if not isinstance(asset, dict) or not isinstance(asset.get("asset_key"), str):
        raise DrawdownWalkForwardEvidenceError(
            "asset event report has invalid identity"
        )

    try:
        if as_of_date is None:
            build_drawdown_profile(asset_event_report)
            series = asset_event_report["drawdown_series"]
            events = asset_event_report["events"]
            outcome = build_drawdown_outcomes(asset_event_report)
            cohort = build_threshold_cohorts(asset_event_report)
        else:
            series, events = _visible_facts(
                asset_event_report.get("drawdown_series"),
                asset["asset_key"],
                as_of_date,
            )
            outcome = build_drawdown_outcomes(
                asset_event_report, as_of_date=as_of_date
            )
            cohort = build_threshold_cohorts(
                asset_event_report, as_of_date=as_of_date
            )
        evaluations = _event_evaluations(
            asset_event_report,
            asset["asset_key"],
            events,
            cohort["cohorts"],
            outcome["records"],
        )
    except ValueError as exc:
        raise DrawdownWalkForwardEvidenceError(str(exc)) from exc

    return {
        "period": {
            "first_date": series[0]["date"],
            "last_date": series[-1]["date"],
            "row_count": len(series),
        },
        "summary": _summary(evaluations),
        "event_evaluations": evaluations,
    }


def _visible_facts(
    raw_series: Any, asset_key: str, as_of_date: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prefix = _series_through_as_of(raw_series, as_of_date)
    prices = [_visible_price_row(row) for row in prefix]
    analysis = analyze_drawdown_history(prices, asset_key=asset_key)
    return (
        [point.to_dict() for point in analysis.drawdown_series],
        [event.to_dict() for event in analysis.events],
    )


def _event_evaluations(
    asset_event_report: dict[str, Any],
    asset_key: str,
    events: list[dict[str, Any]],
    cohorts: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cohort_map: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(
        list
    )
    for cohort in cohorts:
        cohort_map[
            (
                cohort["event_id"],
                cohort["threshold_family"],
                cohort["threshold_level"],
            )
        ].append(cohort)
    record_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        record_map[record["record_id"]].append(record)

    result: list[dict[str, Any]] = []
    for event in events:
        training = build_threshold_statistics(
            asset_event_report, as_of_date=event["peak_date"]
        )
        prior_count = event["event_sequence"] - 1
        if training["summary"]["total_event_count"] != prior_count:
            raise DrawdownWalkForwardEvidenceError(
                "training event count includes the current event"
            )
        training_groups = _training_groups(
            training["threshold_statistics"], prior_count
        )
        training_map = {
            (row["threshold_family"], row["threshold_level"]): row
            for row in training_groups
        }
        threshold_evaluations = []
        for family, levels in THRESHOLD_FAMILIES:
            for level, probability_or_fraction in levels:
                matches = cohort_map.get((event["event_id"], family, level), [])
                if len(matches) != 1:
                    raise DrawdownWalkForwardEvidenceError(
                        "event threshold must identify exactly one cohort"
                    )
                test_cohort = matches[0]
                training_group = training_map[(family, level)]
                threshold_evaluations.append(
                    {
                        "evaluation_id": (
                            f"{asset_key}:{event['event_sequence']}:"
                            f"{family}:{level}"
                        ),
                        "threshold_family": family,
                        "threshold_level": level,
                        "threshold_probability_or_fraction": (
                            probability_or_fraction
                        ),
                        "training_group_sha256": training_group[
                            "training_group_sha256"
                        ],
                        "test_cohort": _test_cohort(test_cohort),
                        "test_outcome": _test_outcome(
                            test_cohort, record_map
                        ),
                    }
                )
        result.append(
            {
                "event_id": event["event_id"],
                "event_sequence": event["event_sequence"],
                "peak_date": event["peak_date"],
                "start_date": event["start_date"],
                "event_completed_in_source": event["completed"],
                "training_snapshot": {
                    "training_snapshot_id": (
                        f"{asset_key}:{event['event_sequence']}:"
                        f"{event['peak_date']}"
                    ),
                    "training_cutoff_date": event["peak_date"],
                    "prior_event_count": prior_count,
                    "threshold_group_count": len(training_groups),
                    "statistics_methodology_version": "1.0",
                    "threshold_statistics": training_groups,
                },
                "threshold_evaluations": threshold_evaluations,
            }
        )
    return result


def _training_groups(
    statistics: list[dict[str, Any]], prior_event_count: int
) -> list[dict[str, Any]]:
    expected = [
        (family, level)
        for family, levels in THRESHOLD_FAMILIES
        for level, _ in levels
    ]
    actual = [
        (row["threshold_family"], row["threshold_level"])
        for row in statistics
    ]
    if actual != expected:
        raise DrawdownWalkForwardEvidenceError(
            "training threshold group order is invalid"
        )
    groups = []
    for row in statistics:
        if row["coverage"]["total_event_count"] != prior_event_count:
            raise DrawdownWalkForwardEvidenceError(
                "training coverage includes the current event"
            )
        group_hash = _canonical_sha256(row)
        groups.append(
            {
                "threshold_family": row["threshold_family"],
                "threshold_level": row["threshold_level"],
                "threshold_probability_or_fraction": row[
                    "threshold_probability_or_fraction"
                ],
                "training_group_sha256": group_hash,
                "coverage": copy.deepcopy(row["coverage"]),
                "trigger_price_recovery": _compact_recovery(
                    row["trigger_price_recovery"]
                ),
                "peak_recovery": _compact_recovery(row["peak_recovery"]),
                "minimum_outcome": copy.deepcopy(row["minimum_outcome"]),
                "horizon_outcomes": copy.deepcopy(row["horizon_outcomes"]),
            }
        )
    return groups


def _compact_recovery(recovery: dict[str, Any]) -> dict[str, Any]:
    return {
        field: copy.deepcopy(recovery[field])
        for field in (
            "sample_count",
            "observed_count",
            "censored_count",
            "naive_observed_fraction",
            "median_recovery_sessions",
            "fixed_horizons",
        )
    }


def _test_cohort(cohort: dict[str, Any]) -> dict[str, Any]:
    return {
        field: copy.deepcopy(cohort[field])
        for field in (
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
    }


def _test_outcome(
    cohort: dict[str, Any], record_map: dict[str, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    status = cohort["threshold_status"]
    selected_id = cohort["selected_record_id"]
    if status in {"insufficient_history", "not_reached"}:
        if selected_id is not None:
            raise DrawdownWalkForwardEvidenceError(
                "non-reached cohort cannot select an outcome"
            )
        return None
    if status != "reached":
        raise DrawdownWalkForwardEvidenceError("invalid cohort threshold status")
    matches = record_map.get(selected_id, [])
    if len(matches) != 1:
        raise DrawdownWalkForwardEvidenceError(
            "reached cohort must select exactly one outcome"
        )
    record = matches[0]
    expected = {
        "event_id": record["event_id"],
        "event_sequence": record["event_sequence"],
        "selected_frontier_sequence": record["frontier_sequence"],
        "trigger_date": record["trigger_date"],
        "trigger_depth": record["trigger_depth"],
        "trigger_drawdown": record["trigger_drawdown"],
    }
    if (
        cohort["asset_key"] != record["asset_key"]
        or any(cohort.get(field) != value for field, value in expected.items())
    ):
        raise DrawdownWalkForwardEvidenceError(
            "cohort identity differs from selected outcome"
        )
    return {
        field: copy.deepcopy(record[field])
        for field in (
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
    }


def _summary(event_evaluations: list[dict[str, Any]]) -> dict[str, int]:
    threshold_evaluations = [
        threshold
        for event in event_evaluations
        for threshold in event["threshold_evaluations"]
    ]
    states = Counter(
        row["test_cohort"]["threshold_status"] for row in threshold_evaluations
    )
    return {
        "event_count": len(event_evaluations),
        "training_snapshot_count": len(event_evaluations),
        "threshold_evaluation_count": len(threshold_evaluations),
        "reached_count": states["reached"],
        "not_reached_count": states["not_reached"],
        "insufficient_history_count": states["insufficient_history"],
    }


def _canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _series_through_as_of(series: Any, as_of_date: str) -> list[Any]:
    if not isinstance(series, list) or not series:
        raise DrawdownWalkForwardEvidenceError(
            "drawdown_series must be non-empty"
        )
    if isinstance(as_of_date, str) and as_of_date:
        for index, row in enumerate(series):
            if isinstance(row, dict) and row.get("date") == as_of_date:
                return series[: index + 1]
    raise DrawdownWalkForwardEvidenceError(
        "as_of_date must be an actual input trading date"
    )


def _visible_price_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise DrawdownWalkForwardEvidenceError(
            "visible drawdown row must be an object"
        )
    return {
        "date": row.get("date"),
        "close": row.get("close"),
        "return_basis": "total_return",
    }
