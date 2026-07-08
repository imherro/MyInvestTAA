from __future__ import annotations

from engine.exposure.constraints import clamp_exposure
from engine.exposure.v2.models import (
    DrawdownAwareExposureDecision,
    ExposureV2Decision,
    TrendAwareVolatilityDecision,
)


def trend_aware_volatility_control(
    current_volatility: float,
    trend_score: float,
    target_volatility: float = 12.0,
    positive_trend_threshold: float = 60.0,
    negative_trend_threshold: float = 45.0,
) -> TrendAwareVolatilityDecision:
    if target_volatility <= 0:
        raise ValueError("target_volatility must be positive")
    volatility = max(0.0, float(current_volatility))
    trend = float(trend_score)
    if volatility <= 0:
        return TrendAwareVolatilityDecision(
            volatility_state="unknown_volatility",
            action="hold_exposure",
            multiplier=1.0,
            current_volatility=0.0,
            target_volatility=target_volatility,
            trend_score=round(trend, 4),
            reason="volatility unavailable",
        )
    if volatility > target_volatility:
        if trend >= positive_trend_threshold:
            return TrendAwareVolatilityDecision(
                volatility_state="high_positive_trend",
                action="hold_exposure",
                multiplier=1.0,
                current_volatility=round(volatility, 4),
                target_volatility=target_volatility,
                trend_score=round(trend, 4),
                reason="high volatility is acceptable while trend is positive",
            )
        if trend < negative_trend_threshold:
            return TrendAwareVolatilityDecision(
                volatility_state="high_negative_trend",
                action="reduce_exposure",
                multiplier=round(max(0.70, target_volatility / volatility), 4),
                current_volatility=round(volatility, 4),
                target_volatility=target_volatility,
                trend_score=round(trend, 4),
                reason="high volatility with weak trend is risk",
            )
        return TrendAwareVolatilityDecision(
            volatility_state="high_mixed_trend",
            action="trim_exposure",
            multiplier=0.90,
            current_volatility=round(volatility, 4),
            target_volatility=target_volatility,
            trend_score=round(trend, 4),
            reason="high volatility without strong trend gets a light trim",
        )
    if volatility < target_volatility * 0.75 and trend >= positive_trend_threshold:
        return TrendAwareVolatilityDecision(
            volatility_state="low_positive_trend",
            action="add_exposure",
            multiplier=1.05,
            current_volatility=round(volatility, 4),
            target_volatility=target_volatility,
            trend_score=round(trend, 4),
            reason="low volatility with positive trend allows gradual risk add",
        )
    return TrendAwareVolatilityDecision(
        volatility_state="normal_volatility",
        action="hold_exposure",
        multiplier=1.0,
        current_volatility=round(volatility, 4),
        target_volatility=target_volatility,
        trend_score=round(trend, 4),
        reason="volatility is within trend-aware tolerance",
    )


def drawdown_aware_exposure_control(
    drawdown_pct: float,
    previous_drawdown_pct: float | None = None,
    moderate_drawdown: float = -5.0,
    deep_drawdown: float = -10.0,
) -> DrawdownAwareExposureDecision:
    if moderate_drawdown > 0 or deep_drawdown > 0:
        raise ValueError("drawdown thresholds must be negative")
    if moderate_drawdown < deep_drawdown:
        raise ValueError("moderate_drawdown must be above deep_drawdown")
    drawdown = float(drawdown_pct)
    previous = None if previous_drawdown_pct is None else float(previous_drawdown_pct)
    recovering = previous is not None and drawdown > previous + 0.5
    if drawdown <= deep_drawdown:
        multiplier = 0.85 if recovering else 0.70
        state = "recovering_deep_drawdown" if recovering else "deep_drawdown"
        reason = "deep drawdown recovering gradually" if recovering else "deep drawdown reduces exposure 30%"
    elif drawdown <= moderate_drawdown:
        multiplier = 1.0 if recovering else 0.90
        state = "recovering_moderate_drawdown" if recovering else "moderate_drawdown"
        reason = "moderate drawdown recovering, hold target" if recovering else "moderate drawdown reduces exposure 10%"
    elif recovering and drawdown < 0:
        multiplier = 1.05
        state = "recovering"
        reason = "drawdown recovery restores exposure gradually"
    else:
        multiplier = 1.0
        state = "normal_drawdown"
        reason = "drawdown within normal range"
    return DrawdownAwareExposureDecision(
        drawdown_state=state,
        multiplier=round(multiplier, 4),
        drawdown=round(drawdown, 4),
        previous_drawdown=None if previous is None else round(previous, 4),
        recovering=recovering,
        reason=reason,
    )


def optimize_equity_exposure_v2(
    regime: str,
    base_equity_limit: float,
    current_volatility: float,
    trend_score: float,
    portfolio_drawdown: float,
    breadth: float | None = None,
    previous_equity_target: float | None = None,
    previous_drawdown: float | None = None,
    target_volatility: float = 12.0,
    minimum: float = 20.0,
    maximum: float = 90.0,
    monthly_max_change: float = 10.0,
    moderate_drawdown: float = -5.0,
    deep_drawdown: float = -10.0,
) -> ExposureV2Decision:
    if monthly_max_change <= 0:
        raise ValueError("monthly_max_change must be positive")
    volatility_control = trend_aware_volatility_control(
        current_volatility,
        trend_score,
        target_volatility=target_volatility,
    )
    drawdown_control = drawdown_aware_exposure_control(
        portfolio_drawdown,
        previous_drawdown_pct=previous_drawdown,
        moderate_drawdown=moderate_drawdown,
        deep_drawdown=deep_drawdown,
    )
    reasons = [
        f"{regime} base equity {base_equity_limit:.0f}%",
        volatility_control.reason,
        drawdown_control.reason,
    ]
    breadth_multiplier = _trend_aware_breadth_multiplier(breadth, trend_score)
    if breadth_multiplier < 1.0:
        reasons.append("breadth weak only penalized when trend is not supportive")
    target = clamp_exposure(
        base_equity_limit
        * volatility_control.multiplier
        * drawdown_control.multiplier
        * breadth_multiplier,
        minimum,
        maximum,
    )
    raw_target = target
    if previous_equity_target is not None:
        lower = max(minimum, previous_equity_target - monthly_max_change)
        upper = min(maximum, previous_equity_target + monthly_max_change)
        target = clamp_exposure(target, lower, upper)
        if target != raw_target:
            reasons.append("monthly exposure smoothing")
    return ExposureV2Decision(
        equity_target=target,
        raw_equity_target=raw_target,
        confidence=_confidence(volatility_control, drawdown_control, breadth, trend_score, target != raw_target),
        reason=reasons,
        regime=regime,
        volatility=round(float(current_volatility), 4),
        trend_score=round(float(trend_score), 4),
        drawdown=round(float(portfolio_drawdown), 4),
        breadth=None if breadth is None else round(float(breadth), 4),
        previous_equity_target=None if previous_equity_target is None else round(float(previous_equity_target), 4),
        monthly_max_change=round(float(monthly_max_change), 4),
        volatility_control=volatility_control,
        drawdown_control=drawdown_control,
    )


def _trend_aware_breadth_multiplier(breadth: float | None, trend_score: float) -> float:
    if breadth is None:
        return 1.0
    if float(trend_score) >= 60.0:
        return 1.0
    if breadth < 0.35:
        return 0.90
    if breadth < 0.45 and float(trend_score) < 45.0:
        return 0.95
    return 1.0


def _confidence(
    volatility_control: TrendAwareVolatilityDecision,
    drawdown_control: DrawdownAwareExposureDecision,
    breadth: float | None,
    trend_score: float,
    smoothed: bool,
) -> float:
    confidence = 0.78
    if volatility_control.action == "reduce_exposure":
        confidence -= 0.10
    if drawdown_control.drawdown_state in {"deep_drawdown", "recovering_deep_drawdown"}:
        confidence -= 0.12
    if breadth is not None and breadth < 0.35 and trend_score < 45.0:
        confidence -= 0.08
    if smoothed:
        confidence -= 0.03
    return round(max(0.40, min(0.90, confidence)), 4)
