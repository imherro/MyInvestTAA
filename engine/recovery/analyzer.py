from __future__ import annotations

from datetime import date

from engine.drawdown import DrawdownEvent
from engine.recovery.models import RecoveryEventAnalysis, RecoverySummary
from engine.recovery.statistics import median_number, round_optional


def analyze_recovery_events(
    events: list[DrawdownEvent],
    price_series: list[dict],
    asset_id: str | None = None,
) -> RecoverySummary:
    rows = _normalize_price_series(price_series)
    analyses = [_analyze_event(event, rows) for event in events]
    recovered_events = sum(1 for item in analyses if item.recovered)
    event_count = len(analyses)
    recovery_probability = recovered_events / event_count if event_count else 0.0

    return RecoverySummary(
        asset_id=asset_id,
        event_count=event_count,
        recovered_events=recovered_events,
        recovery_probability=round(recovery_probability, 4),
        median_recovery_days=round_optional(median_number([item.recovery_days for item in analyses]), 0),
        median_forward_return_1y_pct=round_optional(
            median_number([item.forward_return_1y_pct for item in analyses])
        ),
        median_forward_return_2y_pct=round_optional(
            median_number([item.forward_return_2y_pct for item in analyses])
        ),
        median_forward_return_3y_pct=round_optional(
            median_number([item.forward_return_3y_pct for item in analyses])
        ),
        events=analyses,
    )


def _analyze_event(event: DrawdownEvent, rows: list[tuple[date, float]]) -> RecoveryEventAnalysis:
    bottom_date = date.fromisoformat(event.bottom_date)
    bottom_price = _close_on_or_after(rows, bottom_date)
    if bottom_price is None:
        raise ValueError(f"bottom_date not found in price series: {event.bottom_date}")

    return RecoveryEventAnalysis(
        bottom_date=event.bottom_date,
        drawdown_pct=event.drawdown_pct,
        recovered=event.is_recovered,
        recovery_days=event.recovery_days,
        forward_return_1y_pct=_forward_return(rows, bottom_date, bottom_price, 1),
        forward_return_2y_pct=_forward_return(rows, bottom_date, bottom_price, 2),
        forward_return_3y_pct=_forward_return(rows, bottom_date, bottom_price, 3),
    )


def _forward_return(
    rows: list[tuple[date, float]],
    bottom_date: date,
    bottom_price: float,
    years: int,
) -> float | None:
    target = _add_years(bottom_date, years)
    future_price = _close_on_or_after(rows, target)
    if future_price is None:
        return None
    return round((future_price / bottom_price - 1.0) * 100, 4)


def _close_on_or_after(rows: list[tuple[date, float]], target: date) -> float | None:
    for row_date, close in rows:
        if row_date >= target:
            return close
    return None


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def _normalize_price_series(price_series: list[dict]) -> list[tuple[date, float]]:
    rows: list[tuple[date, float]] = []
    for item in price_series:
        if "date" not in item or "close" not in item:
            raise ValueError("each price row must contain date and close")
        close = float(item["close"])
        if close <= 0:
            raise ValueError("close must be positive")
        rows.append((date.fromisoformat(str(item["date"])), close))
    return sorted(rows, key=lambda row: row[0])

