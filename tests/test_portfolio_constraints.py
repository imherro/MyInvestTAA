import pytest

from current_taa.model import build_target_weights


def _asset(asset_id, category="broad_base"):
    return {"asset_id": asset_id, "category": category}


def test_five_regular_assets_are_equal_weighted():
    weights = build_target_weights([_asset(str(index)) for index in range(5)])
    assert weights == {str(index): 0.2 for index in range(5)}


def test_single_asset_cap_is_25_percent():
    weights = build_target_weights([_asset("a"), _asset("b"), _asset("c")])
    assert max(value for key, value in weights.items() if key != "CASH") == 0.25
    assert weights["CASH"] == 0.25


def test_theme_caps_are_applied():
    selected = [_asset("t1", "theme"), _asset("t2", "theme"), _asset("t3", "theme"), _asset("a"), _asset("b")]
    weights = build_target_weights(selected)
    assert weights["t1"] == 0.1
    assert weights["t2"] == 0.1
    assert "t3" not in weights
    assert sum(weights[key] for key in ("t1", "t2")) <= 0.2


def test_weights_always_sum_to_one():
    selected = [_asset("t1", "theme"), _asset("t2", "theme"), _asset("a"), _asset("b"), _asset("c")]
    assert sum(build_target_weights(selected).values()) == pytest.approx(1.0)


def test_empty_selection_is_cash():
    assert build_target_weights([]) == {"CASH": 1.0}
