from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreadthScore:
    theme: str
    breadth_score: float
    advancers: int
    total: int
    advancer_ratio: float
    new_high_ratio: float
    above_ma_ratio: float

    def as_dict(self) -> dict:
        return {
            "theme": self.theme,
            "breadth_score": self.breadth_score,
            "advancers": self.advancers,
            "total": self.total,
            "advancer_ratio": self.advancer_ratio,
            "new_high_ratio": self.new_high_ratio,
            "above_ma_ratio": self.above_ma_ratio,
        }
