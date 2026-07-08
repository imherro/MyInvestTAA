from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioState:
    date: str
    cash: float
    positions: dict[str, float]
    portfolio_value: float
    weights: dict[str, float]

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "cash": self.cash,
            "positions": self.positions,
            "portfolio_value": self.portfolio_value,
            "weights": self.weights,
        }

