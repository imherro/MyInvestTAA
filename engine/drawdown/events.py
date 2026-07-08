from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DrawdownEvent:
    peak_date: str
    bottom_date: str
    recovery_date: str | None
    drawdown_pct: float
    duration_days: int
    recovery_days: int | None
    is_recovered: bool

    def as_dict(self) -> dict:
        return {
            "peak_date": self.peak_date,
            "bottom_date": self.bottom_date,
            "recovery_date": self.recovery_date,
            "drawdown_pct": self.drawdown_pct,
            "duration_days": self.duration_days,
            "recovery_days": self.recovery_days,
            "is_recovered": self.is_recovered,
        }


def detect_drawdown_events(price_series: list[dict]) -> list[DrawdownEvent]:
    rows = _normalize_price_series(price_series)
    if len(rows) < 2:
        return []

    events: list[DrawdownEvent] = []
    peak_date, peak_price = rows[0]
    in_drawdown = False
    bottom_date = peak_date
    bottom_price = peak_price

    for current_date, close in rows[1:]:
        if close >= peak_price:
            if in_drawdown:
                events.append(
                    _build_event(
                        peak_date=peak_date,
                        peak_price=peak_price,
                        bottom_date=bottom_date,
                        bottom_price=bottom_price,
                        recovery_date=current_date,
                    )
                )
                in_drawdown = False
            peak_date = current_date
            peak_price = close
            bottom_date = current_date
            bottom_price = close
            continue

        if not in_drawdown:
            in_drawdown = True
            bottom_date = current_date
            bottom_price = close
        elif close < bottom_price:
            bottom_date = current_date
            bottom_price = close

    if in_drawdown:
        events.append(
            _build_event(
                peak_date=peak_date,
                peak_price=peak_price,
                bottom_date=bottom_date,
                bottom_price=bottom_price,
                recovery_date=None,
            )
        )

    return events


def _build_event(
    peak_date: date,
    peak_price: float,
    bottom_date: date,
    bottom_price: float,
    recovery_date: date | None,
) -> DrawdownEvent:
    drawdown_pct = (bottom_price / peak_price - 1.0) * 100
    duration_days = (bottom_date - peak_date).days
    recovery_days = (recovery_date - peak_date).days if recovery_date else None

    return DrawdownEvent(
        peak_date=peak_date.isoformat(),
        bottom_date=bottom_date.isoformat(),
        recovery_date=recovery_date.isoformat() if recovery_date else None,
        drawdown_pct=round(drawdown_pct, 4),
        duration_days=duration_days,
        recovery_days=recovery_days,
        is_recovered=recovery_date is not None,
    )


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

