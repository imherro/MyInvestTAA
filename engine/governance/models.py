from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyRegistryEntry:
    version: str
    status: str
    metrics: dict
    evidence: dict | None = None
    promotion_score: float | None = None
    validation_windows: int | None = None
    approval_status: str | None = None

    def as_dict(self) -> dict:
        payload = {
            "version": self.version,
            "status": self.status,
            "metrics": self.metrics,
        }
        if self.evidence is not None:
            payload["evidence"] = self.evidence
        if self.promotion_score is not None:
            payload["promotion_score"] = self.promotion_score
        if self.validation_windows is not None:
            payload["validation_windows"] = self.validation_windows
        if self.approval_status is not None:
            payload["approval_status"] = self.approval_status
        return payload


@dataclass(frozen=True)
class StrategyRegistry:
    production_candidate: str | None
    rows: list[StrategyRegistryEntry]

    def as_dict(self) -> dict:
        return {
            "production_candidate": self.production_candidate,
            "rows": [row.as_dict() for row in self.rows],
        }
