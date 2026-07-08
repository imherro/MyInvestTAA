from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrendAwareVolatilityDecision:
    volatility_state: str
    action: str
    multiplier: float
    current_volatility: float
    target_volatility: float
    trend_score: float
    reason: str

    def as_dict(self) -> dict:
        return {
            "volatility_state": self.volatility_state,
            "action": self.action,
            "multiplier": self.multiplier,
            "current_volatility": self.current_volatility,
            "target_volatility": self.target_volatility,
            "trend_score": self.trend_score,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DrawdownAwareExposureDecision:
    drawdown_state: str
    multiplier: float
    drawdown: float
    previous_drawdown: float | None
    recovering: bool
    reason: str

    def as_dict(self) -> dict:
        return {
            "drawdown_state": self.drawdown_state,
            "multiplier": self.multiplier,
            "drawdown": self.drawdown,
            "previous_drawdown": self.previous_drawdown,
            "recovering": self.recovering,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ExposureV2Decision:
    equity_target: float
    raw_equity_target: float
    confidence: float
    reason: list[str]
    regime: str
    volatility: float
    trend_score: float
    drawdown: float
    breadth: float | None
    previous_equity_target: float | None
    monthly_max_change: float
    volatility_control: TrendAwareVolatilityDecision
    drawdown_control: DrawdownAwareExposureDecision

    def as_dict(self) -> dict:
        return {
            "equity_target": self.equity_target,
            "raw_equity_target": self.raw_equity_target,
            "confidence": self.confidence,
            "reason": self.reason,
            "regime": self.regime,
            "volatility": self.volatility,
            "trend_score": self.trend_score,
            "drawdown": self.drawdown,
            "breadth": self.breadth,
            "previous_equity_target": self.previous_equity_target,
            "monthly_max_change": self.monthly_max_change,
            "volatility_control": self.volatility_control.as_dict(),
            "drawdown_control": self.drawdown_control.as_dict(),
        }
