from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllocationItem:
    asset_id: str
    name: str
    weight: float
    status: str
    opportunity_score: float | None = None

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "weight": self.weight,
            "status": self.status,
            "opportunity_score": self.opportunity_score,
        }


@dataclass(frozen=True)
class AllocationRecommendation:
    risk_level: str
    max_weight: float
    min_cash: float
    market_regime: str
    equity_limit: float
    cash_weight: float
    allocation: list[AllocationItem]

    def as_dict(self) -> dict:
        return {
            "risk_level": self.risk_level,
            "max_weight": self.max_weight,
            "min_cash": self.min_cash,
            "market_regime": self.market_regime,
            "equity_limit": self.equity_limit,
            "cash_weight": self.cash_weight,
            "allocation": [item.as_dict() for item in self.allocation],
            "total_weight": round(sum(item.weight for item in self.allocation), 4),
        }
