from __future__ import annotations

from typing import Any

from current_taa.drawdown_events import analyze_drawdown_history
from current_taa.drawdown_profiles import build_drawdown_profile


HORIZONS = ((63, "3m"), (126, "6m"), (252, "1y"), (504, "2y"), (756, "3y"))


class DrawdownOutcomeError(ValueError):
    pass


def build_drawdown_outcomes(
    asset_event_report: dict[str, Any], *, as_of_date: str | None = None
) -> dict[str, Any]:
    if not isinstance(asset_event_report, dict):
        raise DrawdownOutcomeError("asset event report must be an object")
    status = asset_event_report.get("analysis_status")
    if status == "blocked":
        return {"period": None, "summary": _summary([], []), "records": []}
    if status != "analyzed":
        raise DrawdownOutcomeError("asset event report must be analyzed or blocked")
    asset = asset_event_report.get("asset")
    if not isinstance(asset, dict) or not isinstance(asset.get("asset_key"), str):
        raise DrawdownOutcomeError("asset event report has invalid identity")

    if as_of_date is None:
        build_drawdown_profile(asset_event_report)
        series = asset_event_report["drawdown_series"]
        events = asset_event_report["events"]
    else:
        prefix = _series_through_as_of(
            asset_event_report.get("drawdown_series"), as_of_date
        )
        prices = [_visible_price_row(row) for row in prefix]
        analysis = analyze_drawdown_history(prices, asset_key=asset["asset_key"])
        series = [point.to_dict() for point in analysis.drawdown_series]
        events = [event.to_dict() for event in analysis.events]

    records = _records(asset["asset_key"], series, events)
    return {
        "period": {
            "first_date": series[0]["date"],
            "last_date": series[-1]["date"],
            "row_count": len(series),
        },
        "summary": _summary(events, records),
        "records": records,
    }


def _records(
    asset_key: str, series: list[dict[str, Any]], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    date_indexes = {row["date"]: index for index, row in enumerate(series)}
    records: list[dict[str, Any]] = []
    for event in events:
        event_id = event["event_id"]
        underwater = [
            (index, row)
            for index, row in enumerate(series)
            if row["state"] == "underwater" and row["event_id"] == event_id
        ]
        running_min: float | None = None
        prior_depth: float | None = None
        frontier_sequence = 0
        terminal_index = (
            date_indexes[event["recovery_date"]]
            if event["completed"]
            else len(series) - 1
        )
        for trigger_index, row in underwater:
            drawdown = float(row["drawdown"])
            if running_min is not None and drawdown >= running_min:
                continue
            running_min = drawdown
            frontier_sequence += 1
            trigger_depth = _rounded(-drawdown)
            record = {
                "record_id": (
                    f"{asset_key}:{event['event_sequence']}:{frontier_sequence}"
                ),
                "asset_key": asset_key,
                "event_id": event_id,
                "event_sequence": event["event_sequence"],
                "frontier_sequence": frontier_sequence,
                "event_completed_in_source": event["completed"],
                "trigger_date": row["date"],
                "trigger_series_index": trigger_index,
                "trigger_close": _rounded(float(row["close"])),
                "trigger_drawdown": _rounded(drawdown),
                "trigger_depth": trigger_depth,
                "prior_frontier_depth": prior_depth,
                "depth_increment": (
                    _rounded(trigger_depth - prior_depth)
                    if prior_depth is not None
                    else None
                ),
                "minimum_outcome": _minimum_outcome(
                    series, trigger_index, terminal_index, event["completed"]
                ),
                "trigger_price_recovery": _trigger_recovery(
                    series, trigger_index, terminal_index
                ),
                "peak_recovery": _peak_recovery(
                    event, trigger_index, date_indexes
                ),
                "horizons": [
                    _horizon(series, trigger_index, sessions, label)
                    for sessions, label in HORIZONS
                ],
            }
            records.append(record)
            prior_depth = trigger_depth
    return records


def _minimum_outcome(
    series: list[dict[str, Any]],
    trigger_index: int,
    terminal_index: int,
    completed: bool,
) -> dict[str, Any]:
    window = series[trigger_index : terminal_index + 1]
    minimum_offset = min(range(len(window)), key=lambda index: window[index]["close"])
    minimum_index = trigger_index + minimum_offset
    trigger_close = float(series[trigger_index]["close"])
    minimum_close = float(series[minimum_index]["close"])
    return {
        "status": "realized" if completed else "censored",
        "minimum_date": series[minimum_index]["date"],
        "minimum_close": _rounded(minimum_close),
        "minimum_series_index": minimum_index,
        "additional_return_from_trigger": _rounded(
            minimum_close / trigger_close - 1
        ),
        "sessions_from_trigger": minimum_index - trigger_index,
    }


def _trigger_recovery(
    series: list[dict[str, Any]], trigger_index: int, terminal_index: int
) -> dict[str, Any]:
    trigger_close = float(series[trigger_index]["close"])
    for index in range(trigger_index + 1, terminal_index + 1):
        close = float(series[index]["close"])
        if close >= trigger_close:
            return {
                "status": "observed",
                "date": series[index]["date"],
                "series_index": index,
                "sessions_from_trigger": index - trigger_index,
                "return_at_recovery": _rounded(close / trigger_close - 1),
            }
    return {
        "status": "censored",
        "date": None,
        "series_index": None,
        "sessions_from_trigger": None,
        "return_at_recovery": None,
    }


def _peak_recovery(
    event: dict[str, Any], trigger_index: int, date_indexes: dict[str, int]
) -> dict[str, Any]:
    if not event["completed"]:
        return {
            "status": "censored",
            "date": None,
            "series_index": None,
            "sessions_from_trigger": None,
        }
    recovery_index = date_indexes[event["recovery_date"]]
    return {
        "status": "observed",
        "date": event["recovery_date"],
        "series_index": recovery_index,
        "sessions_from_trigger": recovery_index - trigger_index,
    }


def _horizon(
    series: list[dict[str, Any]], trigger_index: int, sessions: int, label: str
) -> dict[str, Any]:
    end_index = trigger_index + sessions
    base = {"horizon_sessions": sessions, "label": label}
    if end_index >= len(series):
        return {
            **base,
            "status": "censored",
            "end_date": None,
            "end_close": None,
            "forward_return": None,
            "maximum_adverse_excursion": None,
            "maximum_favorable_excursion": None,
        }
    trigger_close = float(series[trigger_index]["close"])
    path_returns = [
        float(row["close"]) / trigger_close - 1
        for row in series[trigger_index : end_index + 1]
    ]
    end_close = float(series[end_index]["close"])
    return {
        **base,
        "status": "observed",
        "end_date": series[end_index]["date"],
        "end_close": _rounded(end_close),
        "forward_return": _rounded(end_close / trigger_close - 1),
        "maximum_adverse_excursion": _rounded(min(path_returns)),
        "maximum_favorable_excursion": _rounded(max(path_returns)),
    }


def _summary(events: list[dict], records: list[dict]) -> dict[str, int]:
    return {
        "event_count": len(events),
        "completed_event_count": sum(event["completed"] for event in events),
        "open_event_count": sum(not event["completed"] for event in events),
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


def _series_through_as_of(series: Any, as_of_date: str) -> list[Any]:
    if not isinstance(series, list) or not series:
        raise DrawdownOutcomeError("drawdown_series must be non-empty")
    if isinstance(as_of_date, str) and as_of_date:
        for index, row in enumerate(series):
            if isinstance(row, dict) and row.get("date") == as_of_date:
                return series[: index + 1]
    raise DrawdownOutcomeError("as_of_date must be an actual input trading date")


def _visible_price_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise DrawdownOutcomeError("visible drawdown row must be an object")
    return {
        "date": row.get("date"),
        "close": row.get("close"),
        "return_basis": "total_return",
    }


def _rounded(value: float) -> float:
    rounded = round(value, 10)
    return 0.0 if rounded == 0 else rounded
