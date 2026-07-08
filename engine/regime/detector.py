from __future__ import annotations

from engine.regime.config import REGIME_EQUITY_LIMITS
from engine.regime.models import MarketRegime


def detect_market_regime(price_series: list[dict]) -> MarketRegime:
    closes = _closes(price_series)
    if len(closes) < 3:
        return _regime("neutral", 0.4, "Insufficient market history; use neutral budget.")

    current = closes[-1]
    ma20 = _moving_average(closes, 20)
    ma60 = _moving_average(closes, 60)
    ma120 = _moving_average(closes, 120)
    current_drawdown = current / max(closes) - 1.0

    if current >= ma20 >= ma60 and current >= ma120 and current_drawdown > -0.05:
        return _regime("bull", 0.75, "Price is above key moving averages with shallow drawdown.")
    if current >= ma20 and current >= ma60 and current_drawdown <= -0.10:
        return _regime("bear_recovery", 0.72, "Market is recovering from a material drawdown.")
    if current < ma60 and current_drawdown <= -0.20:
        return _regime("bear", 0.78, "Price remains below medium trend with deep drawdown.")
    if current >= ma20 and current < ma120:
        return _regime("bear_recovery", 0.65, "Short trend improved while long trend is not repaired.")
    if current < ma20 and current_drawdown > -0.10:
        return _regime("bull_caution", 0.62, "Trend is softening but drawdown remains shallow.")
    return _regime("neutral", 0.6, "Mixed trend and drawdown signals.")


def _regime(state: str, confidence: float, description: str) -> MarketRegime:
    return MarketRegime(
        state=state,
        confidence=confidence,
        equity_limit=REGIME_EQUITY_LIMITS[state],
        description=description,
    )


def _moving_average(values: list[float], window: int) -> float:
    sample = values[-window:] if len(values) >= window else values
    return sum(sample) / len(sample)


def _closes(price_series: list[dict]) -> list[float]:
    closes = [float(row["close"]) for row in price_series]
    if any(close <= 0 for close in closes):
        raise ValueError("close must be positive")
    return closes

