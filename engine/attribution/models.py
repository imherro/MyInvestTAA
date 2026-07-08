from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AttributionReport:
    strategy: str
    contribution: dict[str, float]
    observations: int
    dominant_factor: str
    notes: list[str]

    def as_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "contribution": self.contribution,
            "observations": self.observations,
            "dominant_factor": self.dominant_factor,
            "notes": self.notes,
        }
