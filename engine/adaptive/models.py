from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorWeightSet:
    regime: str
    weights: dict[str, float]
    reason: str

    def as_dict(self) -> dict:
        return {
            "regime": self.regime,
            "weights": self.weights,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AdaptiveScore:
    score: float
    components: dict[str, float]
    factor_weights: FactorWeightSet

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "components": self.components,
            "factor_weights": self.factor_weights.as_dict(),
        }
