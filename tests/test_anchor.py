import pytest

from engine.anchor import (
    anchor_level,
    calculate_anchor_score,
    calculate_profile_anchor_score,
    load_anchor_profile,
    load_anchor_profiles,
)


def test_calculate_profile_anchor_score_uses_weighted_formula():
    profile = calculate_profile_anchor_score(
        {
            "id": "demo",
            "cashflow_score": 100,
            "profitability_score": 80,
            "balance_sheet_score": 60,
            "valuation_anchor_score": 40,
            "lifecycle_score": 20,
        }
    )

    assert profile.asset_id == "demo"
    assert profile.anchor_score == 67.0


def test_calculate_profile_anchor_score_requires_fields():
    with pytest.raises(ValueError):
        calculate_profile_anchor_score({"id": "bad", "cashflow_score": 50})


def test_calculate_profile_anchor_score_validates_range():
    with pytest.raises(ValueError):
        calculate_profile_anchor_score(
            {
                "id": "bad",
                "cashflow_score": 101,
                "profitability_score": 50,
                "balance_sheet_score": 50,
                "valuation_anchor_score": 50,
                "lifecycle_score": 50,
            }
        )


def test_load_anchor_profiles_returns_sample_assets():
    profiles = load_anchor_profiles()

    assert len(profiles) >= 5
    assert profiles["512890"].anchor_score == 85.75


def test_load_anchor_profile_returns_none_for_unknown_asset():
    assert load_anchor_profile("UNKNOWN") is None


def test_calculate_anchor_score_prefers_profile_over_asset_field():
    score = calculate_anchor_score({"id": "512890", "anchor_score": 1})

    assert score == 85.75


def test_anchor_level_thresholds():
    assert anchor_level(80) == "strong"
    assert anchor_level(60) == "medium"
    assert anchor_level(40) == "weak"
    assert anchor_level(20) == "fragile"

