from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExposureDecision:
    equity_target: float
    confidence: float
    reason: list[str]
    regime: str
    volatility: float
    drawdown: float
    breadth: float | None

    def as_dict(self) -> dict:
        return {
            "equity_target": self.equity_target,
            "confidence": self.confidence,
            "reason": self.reason,
            "regime": self.regime,
            "volatility": self.volatility,
            "drawdown": self.drawdown,
            "breadth": self.breadth,
        }
