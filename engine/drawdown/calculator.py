from __future__ import annotations

from dataclasses import dataclass

from engine.drawdown.statistics import pressure_zone


@dataclass(frozen=True)
class DrawdownMetrics:
    current_drawdown_pct: float
    max_drawdown_pct: float
    drawdown_percentile: float
    pressure_zone: str

    def as_dict(self) -> dict:
        return {
            "current_drawdown_pct": self.current_drawdown_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "drawdown_percentile": self.drawdown_percentile,
            "pressure_zone": self.pressure_zone,
        }


def calculate_drawdown(prices: list[float]) -> DrawdownMetrics:
    if not prices:
        raise ValueError("prices must not be empty")
    if any(price <= 0 for price in prices):
        raise ValueError("prices must be positive")

    peak = prices[0]
    drawdowns: list[float] = []
    for price in prices:
        peak = max(peak, price)
        drawdown = (price / peak - 1.0) * 100
        drawdowns.append(drawdown)

    current_drawdown = drawdowns[-1]
    max_drawdown = min(drawdowns)
    percentile = _drawdown_percentile(current_drawdown, drawdowns)

    return DrawdownMetrics(
        current_drawdown_pct=round(current_drawdown, 4),
        max_drawdown_pct=round(max_drawdown, 4),
        drawdown_percentile=round(percentile, 4),
        pressure_zone=pressure_zone(percentile),
    )


def drawdown_score(metrics: DrawdownMetrics) -> float:
    return round(metrics.drawdown_percentile * 100, 2)


def _drawdown_percentile(current_drawdown: float, drawdowns: list[float]) -> float:
    current_severity = abs(min(current_drawdown, 0))
    historical_severity = [abs(min(item, 0)) for item in drawdowns]
    max_severity = max(historical_severity)
    if max_severity == 0:
        return 0.0
    return min(1.0, current_severity / max_severity)

