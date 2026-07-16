from __future__ import annotations

import math
from datetime import date
from typing import Any, Sequence

from current_taa.drawdown_events import analyze_drawdown_history


DEPTH_PERCENTILES = {
    "p50": 0.50,
    "p60": 0.60,
    "p70": 0.70,
    "p75": 0.75,
    "p80": 0.80,
    "p85": 0.85,
    "p90": 0.90,
    "p95": 0.95,
    "p97_5": 0.975,
}
DURATION_PERCENTILES = {"p50": 0.50, "p75": 0.75, "p90": 0.90, "p95": 0.95}
DAILY_STATES = {"high_watermark", "underwater", "recovered"}


class DrawdownProfileError(ValueError):
    pass


def linear_quantile(values: Sequence[float], probability: float) -> float | None:
    if not 0 <= probability <= 1:
        raise DrawdownProfileError("probability must be in [0, 1]")
    sample = [_finite_number(value, "quantile value") for value in values]
    if not sample:
        return None
    sample.sort()
    position = (len(sample) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    value = sample[lower] + (position - lower) * (sample[upper] - sample[lower])
    return _rounded(value)


def build_drawdown_profile(
    asset_event_report: dict[str, Any], *, as_of_date: str | None = None
) -> dict[str, Any]:
    if not isinstance(asset_event_report, dict):
        raise DrawdownProfileError("asset event report must be an object")
    if asset_event_report.get("analysis_status") == "blocked":
        return {
            "daily_depth_profile": None,
            "event_depth_profile": None,
            "duration_profile": None,
            "current_position": None,
        }
    if asset_event_report.get("analysis_status") != "analyzed":
        raise DrawdownProfileError("asset event report must be analyzed or blocked")
    asset = asset_event_report.get("asset")
    if not isinstance(asset, dict) or not isinstance(asset.get("asset_key"), str):
        raise DrawdownProfileError("asset event report has invalid identity")

    if as_of_date is None:
        series, events = _validate_complete_event_report(asset_event_report)
    else:
        prefix = _series_through_as_of(
            asset_event_report.get("drawdown_series"), as_of_date
        )
        price_rows = [_visible_price_row(row) for row in prefix]
        analysis = analyze_drawdown_history(price_rows, asset_key=asset["asset_key"])
        series = [point.to_dict() for point in analysis.drawdown_series]
        events = [event.to_dict() for event in analysis.events]
    return _profile_from_facts(series, events)


def _profile_from_facts(series: list[dict], events: list[dict]) -> dict[str, Any]:
    all_depths = [_depth(row["drawdown"], "daily drawdown") for row in series]
    underwater_depths = [
        _depth(row["drawdown"], "daily drawdown")
        for row in series
        if row["drawdown"] < 0
    ]
    completed = [event for event in events if event["completed"] is True]
    opened = [event for event in events if event["completed"] is False]
    completed_depths = [
        _event_depth(event["max_drawdown"]) for event in completed
    ]
    current = series[-1]
    current_depth = _depth(current["drawdown"], "current drawdown")
    open_event = opened[0] if opened else None
    open_profile = _open_event_profile(open_event, current)

    return {
        "period": {
            "first_date": series[0]["date"],
            "last_date": series[-1]["date"],
            "row_count": len(series),
        },
        "daily_depth_profile": {
            "all_observations": _daily_distribution(
                all_depths, "all_observations", len(underwater_depths)
            ),
            "underwater_observations": _daily_distribution(
                underwater_depths, "underwater_observations", len(underwater_depths)
            ),
        },
        "event_depth_profile": {
            "completed_events": {
                "completed_event_count": len(completed_depths),
                **_distribution(completed_depths, DEPTH_PERCENTILES),
            },
            "current_open_event": open_profile,
        },
        "duration_profile": {
            field: _duration_distribution(
                [event[field] for event in completed], DURATION_PERCENTILES
            )
            for field in (
                "decline_sessions",
                "recovery_sessions",
                "event_span_sessions",
                "underwater_observations",
            )
        },
        "current_position": {
            "date": current["date"],
            "state": current["state"],
            "current_drawdown": _rounded(current["drawdown"]),
            "current_depth": current_depth,
            "all_observations_percentile": _inclusive_percentile(
                all_depths, current_depth
            ),
            "underwater_observations_percentile": (
                _inclusive_percentile(underwater_depths, current_depth)
                if current["drawdown"] < 0
                else None
            ),
            "all_observations_exceedance_rate": _inclusive_exceedance(
                all_depths, current_depth
            ),
            "underwater_observations_exceedance_rate": (
                _inclusive_exceedance(underwater_depths, current_depth)
                if current["drawdown"] < 0
                else None
            ),
            "open_event_depth_position": (
                {
                    "completed_event_depth_percentile": _inclusive_percentile(
                        completed_depths, open_profile["max_depth_to_date"]
                    ),
                    "completed_event_depth_exceedance_rate": _inclusive_exceedance(
                        completed_depths, open_profile["max_depth_to_date"]
                    ),
                }
                if open_profile is not None
                else None
            ),
        },
    }


def _validate_complete_event_report(
    report: dict[str, Any],
) -> tuple[list[dict], list[dict]]:
    series = report.get("drawdown_series")
    events = report.get("events")
    period = report.get("period")
    summary = report.get("event_summary")
    if not isinstance(series, list) or not series:
        raise DrawdownProfileError("drawdown_series must be non-empty")
    if (
        not isinstance(events, list)
        or not isinstance(period, dict)
        or not isinstance(summary, dict)
    ):
        raise DrawdownProfileError("event report structure is invalid")
    previous_date: str | None = None
    underwater_rows = 0
    for row in series:
        if not isinstance(row, dict):
            raise DrawdownProfileError("drawdown row must be an object")
        row_date = row.get("date")
        close = _finite_number(row.get("close"), "daily close")
        drawdown = _finite_number(row.get("drawdown"), "daily drawdown")
        state = row.get("state")
        if not isinstance(row_date, str) or not _is_iso_date(row_date):
            raise DrawdownProfileError("drawdown dates must use YYYY-MM-DD")
        if previous_date is not None and row_date <= previous_date:
            raise DrawdownProfileError("drawdown dates must be strictly increasing")
        if close <= 0 or not -1 < drawdown <= 0:
            raise DrawdownProfileError("daily close or drawdown is out of range")
        if state not in DAILY_STATES:
            raise DrawdownProfileError("invalid daily state")
        if state == "underwater" and drawdown >= 0:
            raise DrawdownProfileError("underwater row must have negative drawdown")
        if state in {"high_watermark", "recovered"} and drawdown != 0:
            raise DrawdownProfileError("non-underwater row must have zero drawdown")
        if state == "high_watermark" and row.get("event_id") is not None:
            raise DrawdownProfileError("high-watermark row cannot have event_id")
        if state in {"underwater", "recovered"} and not row.get("event_id"):
            raise DrawdownProfileError("underwater and recovered rows require event_id")
        if state == "underwater":
            underwater_rows += 1
        previous_date = row_date
    if (
        period.get("row_count") != len(series)
        or period.get("first_date") != series[0]["date"]
        or period.get("last_date") != series[-1]["date"]
    ):
        raise DrawdownProfileError("event report period differs from series")

    event_ids: set[str] = set()
    open_count = 0
    completed_count = 0
    underwater_events = 0
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("event_sequence") != index:
            raise DrawdownProfileError("event sequence must be continuous")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or event_id in event_ids:
            raise DrawdownProfileError("event_id must be unique")
        event_ids.add(event_id)
        _event_depth(event.get("max_drawdown"))
        for field in ("decline_sessions", "event_span_sessions"):
            _nonnegative_integer(event.get(field), f"event {field}")
        underwater = event.get("underwater_observations")
        if (
            not isinstance(underwater, int)
            or isinstance(underwater, bool)
            or underwater <= 0
        ):
            raise DrawdownProfileError("event underwater count is invalid")
        underwater_events += underwater
        if event.get("completed") is True:
            completed_count += 1
            if (
                event.get("recovery_date") is None
                or event.get("recovery_sessions") is None
            ):
                raise DrawdownProfileError("completed event requires recovery fields")
            _nonnegative_integer(
                event.get("recovery_sessions"), "event recovery_sessions"
            )
        elif event.get("completed") is False:
            open_count += 1
            if (
                index != len(events)
                or event.get("recovery_date") is not None
                or event.get("recovery_sessions") is not None
            ):
                raise DrawdownProfileError(
                    "open event must be final with null recovery"
                )
        else:
            raise DrawdownProfileError("event completed must be boolean")
    if open_count > 1 or underwater_events != underwater_rows:
        raise DrawdownProfileError("event and daily underwater counts differ")
    referenced_ids = {
        row.get("event_id") for row in series if row.get("event_id") is not None
    }
    if referenced_ids != event_ids:
        raise DrawdownProfileError("daily and event identifiers differ")
    if (
        summary.get("completed_event_count") != completed_count
        or summary.get("open_event_count") != open_count
        or summary.get("total_event_count") != len(events)
    ):
        raise DrawdownProfileError("event summary differs from events")
    return series, events


def _series_through_as_of(series: Any, as_of_date: str) -> list[Any]:
    if not isinstance(series, list) or not series:
        raise DrawdownProfileError("drawdown_series must be non-empty")
    if isinstance(as_of_date, str) and as_of_date:
        for index, row in enumerate(series):
            if isinstance(row, dict) and row.get("date") == as_of_date:
                return series[: index + 1]
    raise DrawdownProfileError("as_of_date must be an actual input trading date")


def _visible_price_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise DrawdownProfileError("visible drawdown row must be an object")
    return {
        "date": row.get("date"),
        "close": row.get("close"),
        "return_basis": "total_return",
    }


def _daily_distribution(
    values: list[float], name: str, underwater_count: int
) -> dict[str, Any]:
    result = _distribution(values, DEPTH_PERCENTILES)
    result.update(
        {
            "sample_name": name,
            "zero_depth_count": sum(value == 0 for value in values),
            "underwater_count": underwater_count,
            "underwater_rate": (
                _rounded(underwater_count / len(values))
                if name == "all_observations" and values
                else None
            ),
        }
    )
    return result


def _distribution(
    values: Sequence[float], percentiles: dict[str, float]
) -> dict[str, Any]:
    sample = [_finite_number(value, "distribution value") for value in values]
    return {
        "sample_count": len(sample),
        "minimum": _rounded(min(sample)) if sample else None,
        "maximum": _rounded(max(sample)) if sample else None,
        "mean": _rounded(sum(sample) / len(sample)) if sample else None,
        "percentiles": {
            key: linear_quantile(sample, probability)
            for key, probability in percentiles.items()
        },
    }


def _duration_distribution(
    values: Sequence[int], percentiles: dict[str, float]
) -> dict[str, Any]:
    sample = [_nonnegative_integer(value, "duration value") for value in values]
    return {
        "sample_count": len(sample),
        "minimum": min(sample) if sample else None,
        "maximum": max(sample) if sample else None,
        "mean": _rounded(sum(sample) / len(sample)) if sample else None,
        "percentiles": {
            key: linear_quantile(sample, probability)
            for key, probability in percentiles.items()
        },
    }


def _open_event_profile(event: dict | None, current: dict) -> dict[str, Any] | None:
    if event is None:
        return None
    current_drawdown = _finite_number(current["drawdown"], "current drawdown")
    max_drawdown = _finite_number(event["max_drawdown"], "open max_drawdown")
    return {
        "exists": True,
        "event_id": event["event_id"],
        "peak_date": event["peak_date"],
        "start_date": event["start_date"],
        "trough_date": event["trough_date"],
        "current_date": current["date"],
        "current_drawdown": _rounded(current_drawdown),
        "current_depth": _depth(current_drawdown, "current drawdown"),
        "max_drawdown_to_date": _rounded(max_drawdown),
        "max_depth_to_date": _event_depth(max_drawdown),
        "decline_sessions": event["decline_sessions"],
        "event_span_sessions": event["event_span_sessions"],
        "underwater_observations": event["underwater_observations"],
    }


def _depth(drawdown: Any, name: str) -> float:
    value = _finite_number(drawdown, name)
    if not -1 < value <= 0:
        raise DrawdownProfileError(f"{name} must be in (-1, 0]")
    return _rounded(max(0.0, -value))


def _event_depth(max_drawdown: Any) -> float:
    value = _finite_number(max_drawdown, "event max_drawdown")
    if not -1 < value < 0:
        raise DrawdownProfileError("event max_drawdown must be in (-1, 0)")
    return _rounded(-value)


def _inclusive_percentile(values: Sequence[float], current: float) -> float | None:
    if not values:
        return None
    return _rounded(sum(value <= current for value in values) / len(values))


def _inclusive_exceedance(values: Sequence[float], current: float) -> float | None:
    if not values:
        return None
    return _rounded(sum(value >= current for value in values) / len(values))


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise DrawdownProfileError(f"{name} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DrawdownProfileError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise DrawdownProfileError(f"{name} must be finite")
    return number


def _nonnegative_integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DrawdownProfileError(f"{name} must be a nonnegative integer")
    return value


def _is_iso_date(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _rounded(value: float) -> float:
    rounded = round(value, 10)
    return 0.0 if rounded == 0 else rounded
