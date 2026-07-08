from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyRegistryEntry:
    version: str
    status: str
    metrics: dict

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "status": self.status,
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class StrategyRegistry:
    production_candidate: str | None
    rows: list[StrategyRegistryEntry]

    def as_dict(self) -> dict:
        return {
            "production_candidate": self.production_candidate,
            "rows": [row.as_dict() for row in self.rows],
        }
