from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketRegime:
    state: str
    confidence: float
    equity_limit: float
    description: str

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "confidence": self.confidence,
            "equity_limit": self.equity_limit,
            "description": self.description,
        }

