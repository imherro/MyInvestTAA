from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceAttributionReport:
    strategy: str
    asset_contribution: dict[str, float]
    periods: list[dict]
    top_contributors: list[dict]

    def as_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "asset_contribution": self.asset_contribution,
            "periods": self.periods,
            "top_contributors": self.top_contributors,
        }
