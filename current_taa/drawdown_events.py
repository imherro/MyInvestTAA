from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


class DrawdownInputError(ValueError):
    pass


@dataclass(frozen=True)
class DrawdownPoint:
    date: str
    close: float
    high_watermark: float
    high_watermark_date: str
    drawdown: float
    event_id: str | None
    state: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["high_watermark"] = _rounded(self.high_watermark)
        value["drawdown"] = _rounded(self.drawdown)
        return value


@dataclass(frozen=True)
class DrawdownEvent:
    event_id: str
    event_sequence: int
    asset_key: str
    completed: bool
    peak_date: str
    peak_value: float
    start_date: str
    trough_date: str
    trough_value: float
    max_drawdown: float
    recovery_date: str | None
    last_observation_date: str
    decline_sessions: int
    recovery_sessions: int | None
    event_span_sessions: int
    underwater_observations: int

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in ("peak_value", "trough_value", "max_drawdown"):
            value[field] = _rounded(value[field])
        return value


@dataclass(frozen=True)
class DrawdownAnalysis:
    asset_key: str
    first_date: str
    last_date: str
    row_count: int
    events: tuple[DrawdownEvent, ...]
    drawdown_series: tuple[DrawdownPoint, ...]

    @property
    def current_state(self) -> dict[str, Any]:
        point = self.drawdown_series[-1]
        open_event = next(
            (event for event in reversed(self.events) if not event.completed), None
        )
        value = point.to_dict()
        value["open_event"] = open_event.to_dict() if open_event else None
        return value


@dataclass
class _OpenEvent:
    event_id: str
    event_sequence: int
    asset_key: str
    peak_index: int
    peak_date: str
    peak_value: float
    start_date: str
    trough_index: int
    trough_date: str
    trough_value: float
    underwater_observations: int


def analyze_drawdown_history(
    rows: list[dict[str, Any]],
    *,
    asset_key: str,
    as_of_date: str | None = None,
) -> DrawdownAnalysis:
    if not isinstance(asset_key, str) or not asset_key:
        raise DrawdownInputError("asset_key must be non-empty")
    validated = _validate_rows(rows)
    if as_of_date is not None:
        dates = [row["date"] for row in validated]
        if as_of_date not in dates:
            raise DrawdownInputError("as_of_date must be an actual input trading date")
        validated = validated[: dates.index(as_of_date) + 1]

    high_watermark = validated[0]["close"]
    high_watermark_date = validated[0]["date"]
    high_watermark_index = 0
    events: list[DrawdownEvent] = []
    series: list[DrawdownPoint] = [
        DrawdownPoint(
            date=high_watermark_date,
            close=high_watermark,
            high_watermark=high_watermark,
            high_watermark_date=high_watermark_date,
            drawdown=0.0,
            event_id=None,
            state="high_watermark",
        )
    ]
    open_event: _OpenEvent | None = None

    for index, row in enumerate(validated[1:], start=1):
        current_date = row["date"]
        close = row["close"]
        if open_event is None:
            if close >= high_watermark:
                high_watermark = close
                high_watermark_date = current_date
                high_watermark_index = index
                series.append(
                    _point(
                        current_date,
                        close,
                        high_watermark,
                        high_watermark_date,
                        None,
                        "high_watermark",
                    )
                )
                continue
            event_id = f"{asset_key}:{high_watermark_date}"
            open_event = _OpenEvent(
                event_id=event_id,
                event_sequence=len(events) + 1,
                asset_key=asset_key,
                peak_index=high_watermark_index,
                peak_date=high_watermark_date,
                peak_value=high_watermark,
                start_date=current_date,
                trough_index=index,
                trough_date=current_date,
                trough_value=close,
                underwater_observations=1,
            )
            series.append(
                _point(
                    current_date,
                    close,
                    high_watermark,
                    high_watermark_date,
                    event_id,
                    "underwater",
                )
            )
            continue

        if close >= open_event.peak_value:
            events.append(_complete_event(open_event, index, current_date))
            event_id = open_event.event_id
            high_watermark = close
            high_watermark_date = current_date
            high_watermark_index = index
            open_event = None
            series.append(
                _point(
                    current_date,
                    close,
                    high_watermark,
                    high_watermark_date,
                    event_id,
                    "recovered",
                )
            )
            continue

        open_event.underwater_observations += 1
        if close < open_event.trough_value:
            open_event.trough_value = close
            open_event.trough_date = current_date
            open_event.trough_index = index
        series.append(
            _point(
                current_date,
                close,
                high_watermark,
                high_watermark_date,
                open_event.event_id,
                "underwater",
            )
        )

    if open_event is not None:
        events.append(
            _open_event(open_event, len(validated) - 1, validated[-1]["date"])
        )
    return DrawdownAnalysis(
        asset_key=asset_key,
        first_date=validated[0]["date"],
        last_date=validated[-1]["date"],
        row_count=len(validated),
        events=tuple(events),
        drawdown_series=tuple(series),
    )


def _validate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise DrawdownInputError("price history must be a non-empty list")
    validated: list[dict[str, Any]] = []
    previous_date: str | None = None
    for row in rows:
        if not isinstance(row, dict):
            raise DrawdownInputError("price row must be an object")
        try:
            row_date = row["date"]
            raw_close = row["close"]
            if isinstance(raw_close, bool):
                raise TypeError
            close = float(raw_close)
            return_basis = row["return_basis"]
        except (KeyError, TypeError, ValueError) as exc:
            raise DrawdownInputError("price row is malformed") from exc
        if not isinstance(row_date, str) or not _is_iso_date(row_date):
            raise DrawdownInputError("price date must use YYYY-MM-DD")
        if previous_date is not None and row_date <= previous_date:
            raise DrawdownInputError("price dates must be strictly increasing and unique")
        if not math.isfinite(close) or close <= 0:
            raise DrawdownInputError("close must be a finite positive number")
        if return_basis != "total_return":
            raise DrawdownInputError("return_basis must be total_return")
        validated.append({"date": row_date, "close": close})
        previous_date = row_date
    return validated


def _point(
    row_date: str,
    close: float,
    high_watermark: float,
    high_watermark_date: str,
    event_id: str | None,
    state: str,
) -> DrawdownPoint:
    return DrawdownPoint(
        date=row_date,
        close=close,
        high_watermark=high_watermark,
        high_watermark_date=high_watermark_date,
        drawdown=close / high_watermark - 1.0,
        event_id=event_id,
        state=state,
    )


def _complete_event(
    event: _OpenEvent, recovery_index: int, recovery_date: str
) -> DrawdownEvent:
    return DrawdownEvent(
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        asset_key=event.asset_key,
        completed=True,
        peak_date=event.peak_date,
        peak_value=event.peak_value,
        start_date=event.start_date,
        trough_date=event.trough_date,
        trough_value=event.trough_value,
        max_drawdown=event.trough_value / event.peak_value - 1.0,
        recovery_date=recovery_date,
        last_observation_date=recovery_date,
        decline_sessions=event.trough_index - event.peak_index,
        recovery_sessions=recovery_index - event.trough_index,
        event_span_sessions=recovery_index - event.peak_index,
        underwater_observations=event.underwater_observations,
    )


def _open_event(
    event: _OpenEvent, last_index: int, last_date: str
) -> DrawdownEvent:
    return DrawdownEvent(
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        asset_key=event.asset_key,
        completed=False,
        peak_date=event.peak_date,
        peak_value=event.peak_value,
        start_date=event.start_date,
        trough_date=event.trough_date,
        trough_value=event.trough_value,
        max_drawdown=event.trough_value / event.peak_value - 1.0,
        recovery_date=None,
        last_observation_date=last_date,
        decline_sessions=event.trough_index - event.peak_index,
        recovery_sessions=None,
        event_span_sessions=last_index - event.peak_index,
        underwater_observations=event.underwater_observations,
    )


def _rounded(value: float) -> float:
    rounded = round(value, 10)
    return 0.0 if rounded == 0 else rounded


def _is_iso_date(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False
