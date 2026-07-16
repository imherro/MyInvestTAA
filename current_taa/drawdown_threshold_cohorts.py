from __future__ import annotations

from collections import defaultdict
from typing import Any

from current_taa.drawdown_events import analyze_drawdown_history
from current_taa.drawdown_outcomes import build_drawdown_outcomes
from current_taa.drawdown_profiles import build_drawdown_profile, linear_quantile


QUANTILE_LEVELS = (
    ("p75", 0.75),
    ("p80", 0.80),
    ("p85", 0.85),
    ("p90", 0.90),
    ("p95", 0.95),
)
FRACTION_LEVELS = (
    ("f50", 0.50),
    ("f60", 0.60),
    ("f70", 0.70),
    ("f80", 0.80),
    ("f90", 0.90),
)
THRESHOLD_FAMILIES = (
    ("underwater_daily_depth_quantile", QUANTILE_LEVELS),
    ("completed_event_depth_quantile", QUANTILE_LEVELS),
    ("historical_max_event_depth_fraction", FRACTION_LEVELS),
)


class DrawdownThresholdCohortError(ValueError):
    pass


def build_threshold_cohorts(
    asset_event_report: dict[str, Any], *, as_of_date: str | None = None
) -> dict[str, Any]:
    if not isinstance(asset_event_report, dict):
        raise DrawdownThresholdCohortError("asset event report must be an object")
    status = asset_event_report.get("analysis_status")
    if status == "blocked":
        return {"period": None, "summary": _summary([], []), "cohorts": []}
    if status != "analyzed":
        raise DrawdownThresholdCohortError(
            "asset event report must be analyzed or blocked"
        )
    asset = asset_event_report.get("asset")
    if not isinstance(asset, dict) or not isinstance(asset.get("asset_key"), str):
        raise DrawdownThresholdCohortError("asset event report has invalid identity")

    try:
        if as_of_date is None:
            build_drawdown_profile(asset_event_report)
            series = asset_event_report["drawdown_series"]
            events = asset_event_report["events"]
            outcome = build_drawdown_outcomes(asset_event_report)
        else:
            series, events = _visible_facts(
                asset_event_report.get("drawdown_series"),
                asset["asset_key"],
                as_of_date,
            )
            outcome = build_drawdown_outcomes(
                asset_event_report, as_of_date=as_of_date
            )
    except ValueError as exc:
        raise DrawdownThresholdCohortError(str(exc)) from exc

    records_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in outcome["records"]:
        records_by_event[record["event_id"]].append(record)
    cohorts = _cohorts(
        asset["asset_key"], series, events, records_by_event
    )
    return {
        "period": {
            "first_date": series[0]["date"],
            "last_date": series[-1]["date"],
            "row_count": len(series),
        },
        "summary": _summary(events, cohorts),
        "cohorts": cohorts,
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


def _cohorts(
    asset_key: str,
    series: list[dict[str, Any]],
    events: list[dict[str, Any]],
    records_by_event: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    cohorts: list[dict[str, Any]] = []
    for event in events:
        peak_date = event["peak_date"]
        daily_sample = [
            (row["date"], _rounded(-float(row["drawdown"])))
            for row in series
            if row["date"] <= peak_date and float(row["drawdown"]) < 0
        ]
        completed_sample = [
            (prior["recovery_date"], _rounded(-float(prior["max_drawdown"])))
            for prior in events
            if prior["completed"] is True
            and prior["recovery_date"] <= peak_date
        ]
        frontier = sorted(
            records_by_event.get(event["event_id"], []),
            key=lambda record: record["frontier_sequence"],
        )
        samples = {
            "underwater_daily_depth_quantile": daily_sample,
            "completed_event_depth_quantile": completed_sample,
            "historical_max_event_depth_fraction": completed_sample,
        }
        for family, levels in THRESHOLD_FAMILIES:
            sample = samples[family]
            depths = [depth for _, depth in sample]
            for level, value in levels:
                threshold = _threshold(family, depths, value)
                cohorts.append(
                    _cohort_row(
                        asset_key,
                        event,
                        family,
                        level,
                        value,
                        threshold,
                        sample,
                        frontier,
                    )
                )
    return cohorts


def _threshold(family: str, depths: list[float], value: float) -> float | None:
    if not depths:
        return None
    if family == "historical_max_event_depth_fraction":
        return _rounded(max(depths) * value)
    return linear_quantile(depths, value)


def _cohort_row(
    asset_key: str,
    event: dict[str, Any],
    family: str,
    level: str,
    probability_or_fraction: float,
    threshold: float | None,
    sample: list[tuple[str, float]],
    frontier: list[dict[str, Any]],
) -> dict[str, Any]:
    selected = (
        next(
            (
                record
                for record in frontier
                if float(record["trigger_depth"]) >= threshold
            ),
            None,
        )
        if threshold is not None
        else None
    )
    if threshold is None:
        status = "insufficient_history"
    else:
        status = "reached" if selected is not None else "not_reached"
    return {
        "cohort_id": (
            f"{asset_key}:{event['event_sequence']}:{family}:{level}"
        ),
        "asset_key": asset_key,
        "event_id": event["event_id"],
        "event_sequence": event["event_sequence"],
        "event_peak_date": event["peak_date"],
        "event_start_date": event["start_date"],
        "event_completed_in_source": event["completed"],
        "estimation_cutoff_date": event["peak_date"],
        "threshold_family": family,
        "threshold_level": level,
        "threshold_probability_or_fraction": probability_or_fraction,
        "threshold_status": status,
        "threshold_depth": threshold,
        "sample_count": len(sample),
        "completed_event_sample_count": (
            len(sample)
            if family != "underwater_daily_depth_quantile"
            else None
        ),
        "sample_start_date": sample[0][0] if sample else None,
        "sample_end_date": sample[-1][0] if sample else None,
        "selected_record_id": selected["record_id"] if selected else None,
        "selected_frontier_sequence": (
            selected["frontier_sequence"] if selected else None
        ),
        "trigger_date": selected["trigger_date"] if selected else None,
        "trigger_depth": selected["trigger_depth"] if selected else None,
        "trigger_drawdown": selected["trigger_drawdown"] if selected else None,
    }


def _summary(events: list[dict], cohorts: list[dict]) -> dict[str, int]:
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


def _series_through_as_of(series: Any, as_of_date: str) -> list[Any]:
    if not isinstance(series, list) or not series:
        raise DrawdownThresholdCohortError("drawdown_series must be non-empty")
    if isinstance(as_of_date, str) and as_of_date:
        for index, row in enumerate(series):
            if isinstance(row, dict) and row.get("date") == as_of_date:
                return series[: index + 1]
    raise DrawdownThresholdCohortError(
        "as_of_date must be an actual input trading date"
    )


def _visible_price_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise DrawdownThresholdCohortError(
            "visible drawdown row must be an object"
        )
    return {
        "date": row.get("date"),
        "close": row.get("close"),
        "return_basis": "total_return",
    }


def _rounded(value: float) -> float:
    rounded = round(value, 10)
    return 0.0 if rounded == 0 else rounded
