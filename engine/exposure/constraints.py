from __future__ import annotations


def clamp_exposure(value: float, minimum: float = 20.0, maximum: float = 90.0) -> float:
    if minimum > maximum:
        raise ValueError("minimum exposure cannot exceed maximum exposure")
    return round(max(minimum, min(maximum, value)), 2)


def volatility_target_exposure(
    base_exposure: float,
    current_volatility: float,
    target_volatility: float = 12.0,
    minimum: float = 20.0,
    maximum: float = 90.0,
) -> float:
    if target_volatility <= 0:
        raise ValueError("target_volatility must be positive")
    if current_volatility <= 0:
        return clamp_exposure(base_exposure, minimum, maximum)
    return clamp_exposure(base_exposure * target_volatility / current_volatility, minimum, maximum)


def drawdown_control_multiplier(drawdown_pct: float) -> float:
    if drawdown_pct <= -10.0:
        return 0.60
    if drawdown_pct <= -5.0:
        return 0.80
    return 1.0


def breadth_control_multiplier(breadth: float | None) -> float:
    if breadth is None:
        return 1.0
    if breadth < 0.40:
        return 0.85
    if breadth < 0.50:
        return 0.95
    return 1.0
