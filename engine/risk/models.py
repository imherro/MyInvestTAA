from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskBudget:
    regime_state: str
    equity_limit: float
    min_cash: float
    max_single_asset: float
    description: str

    def as_dict(self) -> dict:
        return {
            "regime_state": self.regime_state,
            "equity_limit": self.equity_limit,
            "min_cash": self.min_cash,
            "max_single_asset": self.max_single_asset,
            "description": self.description,
        }

