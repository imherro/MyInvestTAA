from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PortfolioState:
    date: str
    cash: float
    positions: dict[str, float]
    portfolio_value: float
    weights: dict[str, float]
    signals: dict = field(default_factory=dict)
    regime: dict | None = None
    selected_assets: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "cash": self.cash,
            "positions": self.positions,
            "portfolio_value": self.portfolio_value,
            "weights": self.weights,
            "signals": self.signals,
            "regime": self.regime,
            "selected_assets": self.selected_assets,
            "reason": self.reason,
        }
