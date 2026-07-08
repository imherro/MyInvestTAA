from __future__ import annotations

from engine.exposure.constraints import (
    breadth_control_multiplier,
    clamp_exposure,
    drawdown_control_multiplier,
    volatility_target_exposure,
)
from engine.exposure.models import ExposureDecision


def optimize_equity_exposure(
    regime: str,
    base_equity_limit: float,
    current_volatility: float,
    portfolio_drawdown: float,
    breadth: float | None = None,
    target_volatility: float = 12.0,
    minimum: float = 20.0,
    maximum: float = 90.0,
) -> ExposureDecision:
    reasons: list[str] = [f"{regime} base equity {base_equity_limit:.0f}%"]
    volatility_target = volatility_target_exposure(
        base_equity_limit,
        current_volatility,
        target_volatility=target_volatility,
        minimum=minimum,
        maximum=maximum,
    )
    if current_volatility > target_volatility:
        reasons.append("volatility rising")
    elif current_volatility > 0 and current_volatility < target_volatility * 0.75:
        reasons.append("volatility contained")

    drawdown_multiplier = drawdown_control_multiplier(portfolio_drawdown)
    if drawdown_multiplier < 1.0:
        reasons.append("portfolio drawdown control")
    breadth_multiplier = breadth_control_multiplier(breadth)
    if breadth_multiplier < 1.0:
        reasons.append("breadth weakening")

    target = clamp_exposure(volatility_target * drawdown_multiplier * breadth_multiplier, minimum, maximum)
    confidence = _confidence(current_volatility, portfolio_drawdown, breadth)
    return ExposureDecision(
        equity_target=target,
        confidence=confidence,
        reason=reasons,
        regime=regime,
        volatility=round(current_volatility, 4),
        drawdown=round(portfolio_drawdown, 4),
        breadth=None if breadth is None else round(breadth, 4),
    )


def _confidence(volatility: float, drawdown: float, breadth: float | None) -> float:
    confidence = 0.75
    if volatility > 18.0:
        confidence -= 0.15
    if drawdown <= -10.0:
        confidence -= 0.15
    if breadth is not None and breadth < 0.45:
        confidence -= 0.10
    return round(max(0.35, min(0.9, confidence)), 4)
