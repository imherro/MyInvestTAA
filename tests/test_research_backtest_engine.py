from dataclasses import replace

import pytest

from backtest.research.data_loader import build_mock_research_price_dataset
from backtest.research.engine import (
    apply_weight_constraints,
    compute_research_scores,
    run_research_backtest,
)
from backtest.research.metrics import annual_return, build_metrics, calmar_ratio, max_drawdown, sharpe_ratio
from backtest.research.models import ResearchBacktestConfig
from backtest.research.universe import load_research_backtest_universe


ASSETS = load_research_backtest_universe()


def _mock_dataset():
    return build_mock_research_price_dataset(ASSETS, periods=520)


def test_run_research_backtest_returns_available_report():
    report = run_research_backtest(ASSETS, _mock_dataset())

    assert report["available"] is True
    assert report["strategy"] == "RESEARCH_TAA_MVP"
    assert report["universe_count"] == 13
    assert report["universe_scope"]["included_asset_count"] == 13
    assert report["universe_scope"]["included_asset_ids"] == sorted(
        asset.asset_id for asset in ASSETS
    )


def test_full_registry_scope_explains_monitor_only_exclusion():
    from engine.asset_registry import load_research_universe

    all_assets = load_research_universe()
    report = run_research_backtest(all_assets, _mock_dataset())
    scope = report["universe_scope"]
    assert scope["registered_asset_count"] == 32
    excluded = {row["asset_id"]: row for row in scope["excluded_assets"]}
    assert excluded["399606.SZ"]["eligible_for_allocation"] is False
    assert excluded["399606.SZ"]["reason"] in {
        "not_eligible_for_allocation",
        "readiness_blocked",
    }


def test_run_research_backtest_outputs_equity_curve_and_allocations():
    report = run_research_backtest(ASSETS, _mock_dataset())

    assert len(report["equity_curve"]) > 100
    assert report["monthly_allocations"]


def test_run_research_backtest_returns_error_for_insufficient_history():
    report = run_research_backtest(ASSETS, build_mock_research_price_dataset(ASSETS, periods=100))

    assert report["available"] is False
    assert "insufficient price history" in report["errors"][0]


def test_compute_research_scores_returns_components():
    price_data = _mock_dataset()
    aligned = {
        "dates": [row.date for row in price_data[ASSETS[0].asset_id]],
        "prices": {asset.asset_id: [row.close for row in rows] for asset, rows in zip(ASSETS, price_data.values())},
    }

    scores = compute_research_scores(ASSETS, aligned, 300)

    first = scores[ASSETS[0].asset_id]
    assert {"score", "momentum_6m", "momentum_12m", "drawdown_resilience"} <= set(first)


def test_apply_weight_constraints_limits_single_asset_weight():
    selected = ASSETS[:3]

    weights = apply_weight_constraints(selected)

    assert all(weight <= 0.25 for asset_id, weight in weights.items() if asset_id != "CASH")


def test_apply_weight_constraints_limits_theme_assets():
    theme_assets = [asset for asset in ASSETS if asset.category == "theme"][:3]
    broad_assets = [asset for asset in ASSETS if asset.category != "theme"][:2]

    weights = apply_weight_constraints([*theme_assets, *broad_assets])
    theme_weight = sum(weights.get(asset.asset_id, 0.0) for asset in theme_assets)

    assert theme_weight <= 0.20
    assert all(weights.get(asset.asset_id, 0.0) <= 0.10 for asset in theme_assets)


def test_apply_weight_constraints_adds_cash_when_caps_bind():
    theme_assets = [asset for asset in ASSETS if asset.category == "theme"][:5]

    weights = apply_weight_constraints(theme_assets)

    assert weights["CASH"] >= 0.79


@pytest.mark.parametrize("allocation", run_research_backtest(ASSETS, build_mock_research_price_dataset(ASSETS, periods=520))["monthly_allocations"][:12])
def test_monthly_allocations_respect_weight_sum(allocation):
    assert sum(allocation["weights"].values()) <= 1.000001


@pytest.mark.parametrize("allocation", run_research_backtest(ASSETS, build_mock_research_price_dataset(ASSETS, periods=520))["monthly_allocations"][:12])
def test_monthly_allocations_respect_theme_cap(allocation):
    asset_lookup = {asset.asset_id: asset for asset in ASSETS}
    theme_weight = sum(
        weight
        for asset_id, weight in allocation["weights"].items()
        if asset_id in asset_lookup and asset_lookup[asset_id].category == "theme"
    )
    assert theme_weight <= 0.200001


def test_metrics_calculation_handles_growth_curve():
    curve = [{"date": "2024-01-01", "value": 1.0}, {"date": "2024-01-02", "value": 1.1}]

    metrics = build_metrics(curve, periods_per_year=1)

    assert metrics["annual_return"] == 0.1
    assert metrics["max_drawdown"] == 0.0


def test_max_drawdown_detects_loss():
    curve = [
        {"date": "2024-01-01", "value": 1.0},
        {"date": "2024-01-02", "value": 0.8},
    ]

    assert max_drawdown(curve) == pytest.approx(-0.2)


def test_sharpe_and_calmar_return_numbers():
    curve = [
        {"date": "2024-01-01", "value": 1.0},
        {"date": "2024-01-02", "value": 1.01},
        {"date": "2024-01-03", "value": 1.02},
    ]

    assert isinstance(sharpe_ratio(curve), float)
    assert isinstance(calmar_ratio(curve), float)
    assert isinstance(annual_return(curve), float)


def test_run_research_backtest_excludes_price_index_when_supplied():
    price_index_like = replace(ASSETS[0], return_basis="price_index")
    data = build_mock_research_price_dataset([price_index_like], periods=520)

    report = run_research_backtest([price_index_like], data, config=ResearchBacktestConfig(min_assets=1))

    assert report["available"] is False
    assert report["excluded_assets"][0]["reason"] == "unsupported_return_basis"
