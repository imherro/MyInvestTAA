import pytest

from engine.adaptive import (
    DEFAULT_ADAPTIVE_WEIGHTS,
    adaptive_score_for_regime,
    adaptive_weight_snapshot,
    factor_weights_for_regime,
    normalize_factor_weights,
    score_with_adaptive_weights,
)
from engine.adaptive.models import FactorWeightSet


def test_default_adaptive_weights_cover_core_regimes():
    assert {"bull", "bull_caution", "neutral", "bear_recovery", "bear"} <= set(DEFAULT_ADAPTIVE_WEIGHTS)


def test_factor_weights_for_bull_increases_relative_strength():
    weights = factor_weights_for_regime("bull")

    assert weights.weights["relative_strength"] > weights.weights["breadth"]


def test_factor_weights_for_bear_increases_quality():
    weights = factor_weights_for_regime("bear")

    assert weights.weights["quality"] == 0.30


def test_factor_weights_for_unknown_falls_back_to_neutral():
    weights = factor_weights_for_regime("unknown")

    assert weights.regime == "neutral"


def test_factor_weight_set_as_dict_contains_reason():
    payload = factor_weights_for_regime("neutral").as_dict()

    assert {"regime", "weights", "reason"} <= set(payload)


def test_normalize_factor_weights_sums_to_one():
    result = normalize_factor_weights({"a": 2, "b": 2})

    assert sum(result.values()) == 1.0


def test_normalize_factor_weights_rejects_zero_total():
    with pytest.raises(ValueError):
        normalize_factor_weights({"a": 0.0})


def test_score_with_adaptive_weights_returns_weighted_score():
    result = score_with_adaptive_weights(
        {"relative_strength": 100, "theme_momentum": 0, "breadth": 0, "trend": 0, "quality": 0},
        FactorWeightSet("test", {"relative_strength": 1.0}, "unit"),
    )

    assert result.score == 100.0


def test_score_with_adaptive_weights_clamps_components():
    result = score_with_adaptive_weights(
        {"relative_strength": 200},
        FactorWeightSet("test", {"relative_strength": 1.0}, "unit"),
    )

    assert result.components["relative_strength"] == 100.0


def test_score_with_adaptive_weights_handles_missing_components():
    result = score_with_adaptive_weights({}, FactorWeightSet("test", {"relative_strength": 1.0}, "unit"))

    assert result.score == 0.0


def test_adaptive_score_for_regime_uses_bull_weights():
    result = adaptive_score_for_regime("bull", {"relative_strength": 100, "theme_momentum": 100})

    assert result.factor_weights.regime == "bull"


def test_adaptive_score_as_dict_contains_factor_weights():
    result = adaptive_score_for_regime("bear", {"quality": 100})

    assert "factor_weights" in result.as_dict()


def test_adaptive_weight_snapshot_contains_weights_pct():
    snapshot = adaptive_weight_snapshot("bull")

    assert snapshot["weights_pct"]["relative_strength"] == 35.0


def test_adaptive_weight_snapshot_preserves_reason():
    snapshot = adaptive_weight_snapshot("bear")

    assert "bear regime" in snapshot["reason"]


def test_bull_weights_sum_to_one():
    assert round(sum(factor_weights_for_regime("bull").weights.values()), 6) == 1.0


def test_bear_weights_sum_to_one():
    assert round(sum(factor_weights_for_regime("bear").weights.values()), 6) == 1.0


def test_neutral_weights_match_v7_style_breadth():
    weights = factor_weights_for_regime("neutral").weights

    assert weights["breadth"] == 0.25


def test_bull_caution_weights_use_more_breadth_than_bull():
    assert factor_weights_for_regime("bull_caution").weights["breadth"] > factor_weights_for_regime("bull").weights["breadth"]


def test_bear_recovery_keeps_theme_momentum():
    assert factor_weights_for_regime("bear_recovery").weights["theme_momentum"] == 0.25


def test_score_with_adaptive_weights_rounds_score():
    result = score_with_adaptive_weights(
        {"relative_strength": 33.3333},
        FactorWeightSet("test", {"relative_strength": 1.0}, "unit"),
    )

    assert result.score == 33.33


def test_score_with_adaptive_weights_ignores_unknown_weight_key():
    result = score_with_adaptive_weights(
        {"relative_strength": 50},
        FactorWeightSet("test", {"relative_strength": 1.0, "unknown": 1.0}, "unit"),
    )

    assert result.score == 25.0


def test_adaptive_score_components_have_all_factor_keys():
    result = adaptive_score_for_regime("neutral", {"breadth": 50})

    assert {"relative_strength", "theme_momentum", "breadth", "trend", "quality"} <= set(result.components)


def test_factor_weights_are_copied():
    weights = factor_weights_for_regime("bull")
    weights.weights["relative_strength"] = 0.0

    assert factor_weights_for_regime("bull").weights["relative_strength"] == 0.35
