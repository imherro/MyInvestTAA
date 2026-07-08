from __future__ import annotations

from engine.adaptive.models import AdaptiveScore, FactorWeightSet
from engine.adaptive.weights import factor_weights_for_regime, normalize_factor_weights


FACTOR_KEYS = ("relative_strength", "theme_momentum", "breadth", "trend", "quality")


def score_with_adaptive_weights(components: dict[str, float], factor_weights: FactorWeightSet) -> AdaptiveScore:
    weights = normalize_factor_weights(factor_weights.weights)
    clean_components = {key: _score_value(components.get(key, 0.0)) for key in FACTOR_KEYS}
    score = round(
        sum(clean_components[key] * weights.get(key, 0.0) for key in FACTOR_KEYS),
        2,
    )
    return AdaptiveScore(score=score, components=clean_components, factor_weights=factor_weights)


def adaptive_score_for_regime(regime_state: str, components: dict[str, float]) -> AdaptiveScore:
    return score_with_adaptive_weights(components, factor_weights_for_regime(regime_state))


def adaptive_weight_snapshot(regime_state: str) -> dict:
    weights = factor_weights_for_regime(regime_state)
    return {
        **weights.as_dict(),
        "weights_pct": {key: round(value * 100.0, 2) for key, value in weights.weights.items()},
    }


def _score_value(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(100.0, score))
