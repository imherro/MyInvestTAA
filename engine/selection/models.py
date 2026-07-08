from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RelativeStrengthScore:
    asset: str
    benchmark: str
    strength_score: float
    weighted_excess_return: float
    windows: dict[str, dict[str, float | None]]

    def as_dict(self) -> dict:
        return {
            "asset": self.asset,
            "benchmark": self.benchmark,
            "strength_score": self.strength_score,
            "weighted_excess_return": self.weighted_excess_return,
            "windows": self.windows,
        }


@dataclass(frozen=True)
class SelectionAttribution:
    baseline: str
    candidate: str
    old: float
    new: float
    improvement: float
    improved: bool

    def as_dict(self) -> dict:
        return {
            "baseline": self.baseline,
            "candidate": self.candidate,
            "selection": {
                "old": self.old,
                "new": self.new,
                "improvement": self.improvement,
                "improved": self.improved,
            },
        }
