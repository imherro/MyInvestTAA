import pytest

from engine.allocation import build_allocation_recommendation
from engine.asset_repository import load_assets


def test_allocation_recommendation_sums_to_one_hundred():
    recommendation = build_allocation_recommendation(load_assets())

    assert recommendation.as_dict()["total_weight"] == 100.0


def test_allocation_recommendation_keeps_minimum_cash():
    recommendation = build_allocation_recommendation(load_assets(), min_cash=10)
    cash = next(item for item in recommendation.allocation if item.asset_id == "CASH")

    assert cash.weight >= 10


def test_allocation_recommendation_caps_single_asset_weight():
    recommendation = build_allocation_recommendation(load_assets(), max_weight=20, min_cash=10)

    asset_weights = [item.weight for item in recommendation.allocation if item.asset_id != "CASH"]
    assert asset_weights
    assert all(weight <= 20 for weight in asset_weights)


def test_allocation_recommendation_returns_cash_only_for_empty_assets():
    recommendation = build_allocation_recommendation([])

    assert recommendation.risk_level == "defensive"
    assert len(recommendation.allocation) == 1
    assert recommendation.allocation[0].asset_id == "CASH"
    assert recommendation.allocation[0].weight == 100.0


def test_allocation_recommendation_rejects_invalid_max_weight():
    with pytest.raises(ValueError):
        build_allocation_recommendation(load_assets(), max_weight=0)


def test_allocation_recommendation_rejects_invalid_min_cash():
    with pytest.raises(ValueError):
        build_allocation_recommendation(load_assets(), min_cash=101)


def test_allocation_recommendation_includes_status():
    recommendation = build_allocation_recommendation(load_assets())

    statuses = {item.status for item in recommendation.allocation}
    assert "reserve" in statuses
    assert statuses <= {"overweight", "underweight", "neutral", "reserve"}

