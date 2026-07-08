from __future__ import annotations

from engine.adaptive.models import FactorWeightSet


DEFAULT_ADAPTIVE_WEIGHTS: dict[str, tuple[dict[str, float], str]] = {
    "bull": (
        {
            "relative_strength": 0.35,
            "theme_momentum": 0.30,
            "breadth": 0.10,
            "trend": 0.15,
            "quality": 0.10,
        },
        "bull regime increases momentum and relative strength",
    ),
    "bull_caution": (
        {
            "relative_strength": 0.20,
            "theme_momentum": 0.20,
            "breadth": 0.25,
            "trend": 0.20,
            "quality": 0.15,
        },
        "bull_caution regime balances breadth confirmation with trend control",
    ),
    "neutral": (
        {
            "relative_strength": 0.20,
            "theme_momentum": 0.25,
            "breadth": 0.25,
            "trend": 0.15,
            "quality": 0.15,
        },
        "neutral regime uses balanced V7-style selection weights",
    ),
    "bear_recovery": (
        {
            "relative_strength": 0.25,
            "theme_momentum": 0.25,
            "breadth": 0.20,
            "trend": 0.15,
            "quality": 0.15,
        },
        "bear_recovery regime keeps momentum while requiring breadth support",
    ),
    "bear": (
        {
            "relative_strength": 0.10,
            "theme_momentum": 0.15,
            "breadth": 0.25,
            "trend": 0.20,
            "quality": 0.30,
        },
        "bear regime increases quality and breadth while reducing chase strength",
    ),
}


def factor_weights_for_regime(regime_state: str) -> FactorWeightSet:
    weights, reason = DEFAULT_ADAPTIVE_WEIGHTS.get(regime_state, DEFAULT_ADAPTIVE_WEIGHTS["neutral"])
    return FactorWeightSet(
        regime=regime_state if regime_state in DEFAULT_ADAPTIVE_WEIGHTS else "neutral",
        weights=dict(weights),
        reason=reason,
    )


def normalize_factor_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(float(value) for value in weights.values())
    if total <= 0:
        raise ValueError("factor weights must sum to a positive value")
    return {key: round(float(value) / total, 6) for key, value in weights.items()}
