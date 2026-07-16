from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Sequence

from current_taa.drawdown_events import analyze_drawdown_history
from current_taa.drawdown_outcomes import HORIZONS, build_drawdown_outcomes
from current_taa.drawdown_profiles import build_drawdown_profile, linear_quantile
from current_taa.drawdown_threshold_cohorts import (
    THRESHOLD_FAMILIES,
    build_threshold_cohorts,
)


class DrawdownThresholdStatisticsError(ValueError):
    pass


def build_threshold_statistics(
    asset_event_report: dict[str, Any], *, as_of_date: str | None = None
) -> dict[str, Any]:
    if not isinstance(asset_event_report, dict):
        raise DrawdownThresholdStatisticsError(
            "asset event report must be an object"
        )
    status = asset_event_report.get("analysis_status")
    if status == "blocked":
        return {
            "period": None,
            "summary": _summary(0, []),
            "threshold_statistics": [],
        }
    if status != "analyzed":
        raise DrawdownThresholdStatisticsError(
            "asset event report must be analyzed or blocked"
        )
    asset = asset_event_report.get("asset")
    if not isinstance(asset, dict) or not isinstance(asset.get("asset_key"), str):
        raise DrawdownThresholdStatisticsError(
            "asset event report has invalid identity"
        )

    try:
        if as_of_date is None:
            build_drawdown_profile(asset_event_report)
            series = asset_event_report["drawdown_series"]
            outcome = build_drawdown_outcomes(asset_event_report)
            cohort = build_threshold_cohorts(asset_event_report)
        else:
            series = _visible_series(
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
        statistics = _threshold_statistics(
            cohort["cohorts"], outcome["records"], series
        )
    except ValueError as exc:
        raise DrawdownThresholdStatisticsError(str(exc)) from exc

    return {
        "period": cohort["period"],
        "summary": _summary(cohort["summary"]["event_count"], statistics),
        "threshold_statistics": statistics,
    }


def _visible_series(
    raw_series: Any, asset_key: str, as_of_date: str
) -> list[dict[str, Any]]:
    prefix = _series_through_as_of(raw_series, as_of_date)
    prices = [_visible_price_row(row) for row in prefix]
    analysis = analyze_drawdown_history(prices, asset_key=asset_key)
    return [point.to_dict() for point in analysis.drawdown_series]


def _threshold_statistics(
    cohorts: list[dict[str, Any]],
    outcome_records: list[dict[str, Any]],
    series: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    record_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in outcome_records:
        record_map[record["record_id"]].append(record)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for cohort in cohorts:
        groups[(cohort["threshold_family"], cohort["threshold_level"])].append(
            cohort
        )

    statistics: list[dict[str, Any]] = []
    for family, levels in THRESHOLD_FAMILIES:
        for level, probability_or_fraction in levels:
            group = groups.get((family, level), [])
            selected = [
                _selected_record(row, record_map)
                for row in group
                if row["threshold_status"] == "reached"
            ]
            statistics.append(
                {
                    "threshold_family": family,
                    "threshold_level": level,
                    "threshold_probability_or_fraction": (
                        probability_or_fraction
                    ),
                    "coverage": _coverage(group),
                    "trigger_price_recovery": _recovery_statistics(
                        group, selected, series, "trigger_price_recovery"
                    ),
                    "peak_recovery": _recovery_statistics(
                        group, selected, series, "peak_recovery"
                    ),
                    "minimum_outcome": _minimum_statistics(selected),
                    "horizon_outcomes": _horizon_statistics(selected),
                }
            )
    return statistics


def _selected_record(
    cohort: dict[str, Any], record_map: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    selected_id = cohort.get("selected_record_id")
    matches = record_map.get(selected_id, [])
    if len(matches) != 1:
        raise DrawdownThresholdStatisticsError(
            "selected_record_id must identify exactly one outcome record"
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
        cohort.get("asset_key") != record.get("asset_key")
        or any(cohort.get(field) != value for field, value in expected.items())
    ):
        raise DrawdownThresholdStatisticsError(
            "cohort selection identity differs from outcome record"
        )
    return record


def _coverage(cohorts: list[dict[str, Any]]) -> dict[str, Any]:
    states = Counter(row["threshold_status"] for row in cohorts)
    total = len(cohorts)
    insufficient = states["insufficient_history"]
    reached = states["reached"]
    not_reached = states["not_reached"]
    available = reached + not_reached
    if insufficient + available != total:
        raise DrawdownThresholdStatisticsError(
            "cohort threshold status is invalid"
        )
    return {
        "total_event_count": total,
        "insufficient_history_count": insufficient,
        "threshold_available_event_count": available,
        "reached_event_count": reached,
        "not_reached_event_count": not_reached,
        "attainment_rate": _ratio(reached, available),
    }


def _recovery_statistics(
    cohorts: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    series: list[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    cohort_by_record = {
        row["selected_record_id"]: row
        for row in cohorts
        if row["threshold_status"] == "reached"
    }
    if len(cohort_by_record) != len(selected):
        raise DrawdownThresholdStatisticsError(
            "a threshold group must contain at most one sample per event"
        )
    samples = [
        _recovery_sample(
            cohort_by_record[record["record_id"]],
            record,
            series,
            field,
        )
        for record in selected
    ]
    return _kaplan_meier(samples)


def _recovery_sample(
    cohort: dict[str, Any],
    record: dict[str, Any],
    series: list[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    recovery = record[field]
    status = recovery.get("status")
    completed = record["event_completed_in_source"]
    if status == "observed":
        time_sessions = recovery.get("sessions_from_trigger")
    elif status == "censored":
        if completed:
            raise DrawdownThresholdStatisticsError(
                "completed event recovery cannot be censored"
            )
        trigger_index = record.get("trigger_series_index")
        if not isinstance(trigger_index, int) or isinstance(trigger_index, bool):
            raise DrawdownThresholdStatisticsError(
                "trigger series index must be an integer"
            )
        time_sessions = len(series) - 1 - trigger_index
    else:
        raise DrawdownThresholdStatisticsError("invalid recovery status")
    if (
        not isinstance(time_sessions, int)
        or isinstance(time_sessions, bool)
        or time_sessions < 0
    ):
        raise DrawdownThresholdStatisticsError(
            "recovery time must be a nonnegative integer"
        )
    return {
        "cohort_id": cohort["cohort_id"],
        "event_id": cohort["event_id"],
        "selected_record_id": record["record_id"],
        "trigger_date": record["trigger_date"],
        "status": status,
        "time_sessions": time_sessions,
    }


def _kaplan_meier(samples: list[dict[str, Any]]) -> dict[str, Any]:
    observed = sum(sample["status"] == "observed" for sample in samples)
    censored = sum(sample["status"] == "censored" for sample in samples)
    if observed + censored != len(samples):
        raise DrawdownThresholdStatisticsError("invalid recovery sample status")
    counts = Counter(
        (sample["time_sessions"], sample["status"]) for sample in samples
    )
    at_risk = len(samples)
    survival = 1.0
    greenwood_sum = 0.0
    timeline: list[dict[str, Any]] = []
    for time_sessions in sorted({sample["time_sessions"] for sample in samples}):
        recoveries = counts[(time_sessions, "observed")]
        censorings = counts[(time_sessions, "censored")]
        if recoveries > at_risk or recoveries + censorings > at_risk:
            raise DrawdownThresholdStatisticsError("invalid Kaplan-Meier risk set")
        survival *= 1 - recoveries / at_risk
        if recoveries and at_risk > recoveries:
            greenwood_sum += recoveries / (
                at_risk * (at_risk - recoveries)
            )
        standard_error = (
            0.0
            if survival == 0
            else math.sqrt(survival * survival * greenwood_sum)
        )
        timeline.append(
            {
                "time_sessions": time_sessions,
                "at_risk": at_risk,
                "observed_recoveries": recoveries,
                "censored": censorings,
                "survival_probability": _rounded(survival),
                "recovery_probability": _rounded(1 - survival),
                "greenwood_standard_error": _rounded(standard_error),
            }
        )
        at_risk -= recoveries + censorings
    median = next(
        (
            row["time_sessions"]
            for row in timeline
            if row["survival_probability"] <= 0.5
        ),
        None,
    )
    return {
        "sample_count": len(samples),
        "observed_count": observed,
        "censored_count": censored,
        "naive_observed_fraction": _ratio(observed, len(samples)),
        "median_recovery_sessions": median,
        "samples": samples,
        "timeline": timeline,
        "fixed_horizons": [
            _km_at_horizon(samples, timeline, sessions, label)
            for sessions, label in HORIZONS
        ],
    }


def _km_at_horizon(
    samples: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    horizon: int,
    label: str,
) -> dict[str, Any]:
    base = {
        "horizon_sessions": horizon,
        "label": label,
        "sample_count": len(samples),
        "observed_recoveries_through_horizon": sum(
            sample["status"] == "observed"
            and sample["time_sessions"] <= horizon
            for sample in samples
        ),
        "censored_through_horizon": sum(
            sample["status"] == "censored"
            and sample["time_sessions"] <= horizon
            for sample in samples
        ),
    }
    if not samples:
        return {
            **base,
            "survival_probability": None,
            "recovery_probability": None,
            "greenwood_standard_error": None,
        }
    visible = [row for row in timeline if row["time_sessions"] <= horizon]
    if visible:
        latest = visible[-1]
        survival = latest["survival_probability"]
        recovery = latest["recovery_probability"]
        standard_error = latest["greenwood_standard_error"]
    else:
        survival, recovery, standard_error = 1.0, 0.0, 0.0
    return {
        **base,
        "survival_probability": survival,
        "recovery_probability": recovery,
        "greenwood_standard_error": standard_error,
    }


def _horizon_statistics(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for horizon_index, (sessions, label) in enumerate(HORIZONS):
        rows = []
        for record in selected:
            horizons = record.get("horizons")
            if not isinstance(horizons, list) or len(horizons) != len(HORIZONS):
                raise DrawdownThresholdStatisticsError(
                    "outcome horizon set is invalid"
                )
            row = horizons[horizon_index]
            if (
                row.get("horizon_sessions") != sessions
                or row.get("label") != label
            ):
                raise DrawdownThresholdStatisticsError(
                    "outcome horizon identity is invalid"
                )
            rows.append(row)
        observed = [row for row in rows if row.get("status") == "observed"]
        censored = [row for row in rows if row.get("status") == "censored"]
        if len(observed) + len(censored) != len(rows):
            raise DrawdownThresholdStatisticsError(
                "outcome horizon status is invalid"
            )
        adverse = [_number(row["maximum_adverse_excursion"]) for row in observed]
        favorable = [
            _number(row["maximum_favorable_excursion"]) for row in observed
        ]
        if any(value > 0 for value in adverse) or any(
            value < 0 for value in favorable
        ):
            raise DrawdownThresholdStatisticsError(
                "outcome excursion has an invalid sign"
            )
        result.append(
            {
                "horizon_sessions": sessions,
                "label": label,
                "observed_window_count": len(observed),
                "censored_window_count": len(censored),
                "forward_return_distribution": _distribution(
                    [_number(row["forward_return"]) for row in observed],
                    return_rates=True,
                ),
                "maximum_adverse_excursion_distribution": _distribution(
                    adverse
                ),
                "maximum_favorable_excursion_distribution": _distribution(
                    favorable
                ),
            }
        )
    return result


def _minimum_statistics(selected: list[dict[str, Any]]) -> dict[str, Any]:
    realized = [
        record["minimum_outcome"]
        for record in selected
        if record["minimum_outcome"].get("status") == "realized"
    ]
    censored = [
        record["minimum_outcome"]
        for record in selected
        if record["minimum_outcome"].get("status") == "censored"
    ]
    if len(realized) + len(censored) != len(selected):
        raise DrawdownThresholdStatisticsError(
            "minimum outcome status is invalid"
        )
    return {
        "realized_count": len(realized),
        "censored_count": len(censored),
        "additional_return_distribution": _distribution(
            [_number(row["additional_return_from_trigger"]) for row in realized]
        ),
        "sessions_to_minimum_distribution": _distribution(
            [row["sessions_from_trigger"] for row in realized]
        ),
    }


def _distribution(
    values: Sequence[float], *, return_rates: bool = False
) -> dict[str, Any]:
    sample = [_number(value) for value in values]
    result = {
        "sample_count": len(sample),
        "minimum": _rounded(min(sample)) if sample else None,
        "p25": linear_quantile(sample, 0.25),
        "p50": linear_quantile(sample, 0.50),
        "p75": linear_quantile(sample, 0.75),
        "maximum": _rounded(max(sample)) if sample else None,
        "mean": _rounded(sum(sample) / len(sample)) if sample else None,
    }
    if return_rates:
        positive = sum(value > 0 for value in sample)
        non_negative = sum(value >= 0 for value in sample)
        result.update(
            {
                "positive_count": positive,
                "positive_rate": _ratio(positive, len(sample)),
                "non_negative_count": non_negative,
                "non_negative_rate": _ratio(non_negative, len(sample)),
            }
        )
    return result


def _summary(
    event_count: int, statistics: list[dict[str, Any]]
) -> dict[str, int]:
    return {
        "threshold_group_count": len(statistics),
        "total_event_count": event_count,
        "total_reached_cohorts": sum(
            row["coverage"]["reached_event_count"] for row in statistics
        ),
    }


def _series_through_as_of(series: Any, as_of_date: str) -> list[Any]:
    if not isinstance(series, list) or not series:
        raise DrawdownThresholdStatisticsError(
            "drawdown_series must be non-empty"
        )
    if isinstance(as_of_date, str) and as_of_date:
        for index, row in enumerate(series):
            if isinstance(row, dict) and row.get("date") == as_of_date:
                return series[: index + 1]
    raise DrawdownThresholdStatisticsError(
        "as_of_date must be an actual input trading date"
    )


def _visible_price_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise DrawdownThresholdStatisticsError(
            "visible drawdown row must be an object"
        )
    return {
        "date": row.get("date"),
        "close": row.get("close"),
        "return_basis": "total_return",
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return _rounded(numerator / denominator) if denominator else None


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise DrawdownThresholdStatisticsError("statistic value must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DrawdownThresholdStatisticsError(
            "statistic value must be finite"
        ) from exc
    if not math.isfinite(number):
        raise DrawdownThresholdStatisticsError("statistic value must be finite")
    return number


def _rounded(value: float) -> float:
    rounded = round(value, 10)
    return 0.0 if rounded == 0 else rounded
