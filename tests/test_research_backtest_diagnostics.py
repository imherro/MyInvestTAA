import pytest

from backtest.research.data_loader import build_mock_research_price_dataset
from backtest.research.engine import run_research_backtest
from backtest.research.universe import load_research_backtest_universe


ASSETS = load_research_backtest_universe()
REPORT = run_research_backtest(ASSETS, build_mock_research_price_dataset(ASSETS, periods=520))


def test_diagnostics_explain_common_sample_alignment():
    sample = REPORT["diagnostics"]["sample_period"]

    assert sample["raw_start"] is not None
    assert sample["aligned_start"] is not None
    assert sample["backtest_start"] == REPORT["period"]["start"]
    assert "252-day lookback" in sample["reason"]


def test_diagnostics_include_cash_drag_and_cap_impact():
    impact = REPORT["diagnostics"]["constraint_impact"]

    assert 0.0 <= impact["average_cash_weight"] <= 1.0
    assert 0.0 <= impact["max_cash_weight"] <= 1.0
    assert impact["theme_cap_hit_months"] >= 0


def test_diagnostics_factor_summary_has_expected_components():
    factors = REPORT["diagnostics"]["factor_summary"]

    assert factors["score_observations"] > 0
    assert factors["average_drawdown_resilience"] is not None


def test_diagnostics_warns_about_sample_period_and_cash_constraints():
    warnings = REPORT["diagnostics"]["warnings"]

    assert any("common-date alignment" in warning for warning in warnings)
    assert any("Cash allocation" in warning for warning in warnings)


@pytest.mark.parametrize("row", REPORT["diagnostics"]["selection_frequency"], ids=lambda row: row["asset_id"])
def test_selection_frequency_rows_describe_assets_that_were_selected(row):
    names = {asset.asset_id: asset.name for asset in ASSETS}

    assert row["asset_id"] in names
    assert row["name"] == names[row["asset_id"]]
    assert row["selected_months"] > 0


def test_selection_frequency_does_not_exceed_rebalance_count():
    rebalance_count = len(REPORT["monthly_allocations"])

    assert all(row["selected_months"] <= rebalance_count for row in REPORT["diagnostics"]["selection_frequency"])


@pytest.mark.parametrize("allocation", REPORT["monthly_allocations"])
def test_each_allocation_contributes_scored_selection_to_diagnostics(allocation):
    assert allocation["scores"]
    assert set(allocation["scores"]) <= {
        row["asset_id"] for row in REPORT["diagnostics"]["selection_frequency"]
    }


@pytest.mark.parametrize("allocation", REPORT["monthly_allocations"])
def test_each_allocation_cash_weight_is_within_diagnostic_bounds(allocation):
    cash = allocation["weights"].get("CASH", 0.0)
    impact = REPORT["diagnostics"]["constraint_impact"]

    assert 0.0 <= cash <= impact["max_cash_weight"] + 1e-8
