import pytest

from backtest.taa import PortfolioState, run_taa_backtest
from backtest.taa.metrics import calculate_taa_metrics, drawdown_curve
from backtest.taa.rebalance import build_rebalance_weights, normalize_weights, turnover
from engine.regime.models import MarketRegime
from engine.risk import build_risk_budget


def test_portfolio_state_as_dict():
    state = PortfolioState("2024-01-01", 0.2, {"A": 0.8}, 1.0, {"A": 80, "CASH": 20})

    payload = state.as_dict()

    assert payload["date"] == "2024-01-01"
    assert payload["weights"]["CASH"] == 20
    assert payload["selected_assets"] == []


def test_normalize_weights_sums_to_one_hundred():
    weights = normalize_weights({"A": 30, "B": 30, "CASH": 30})

    assert round(sum(weights.values()), 4) == 100.0


def test_normalize_weights_returns_cash_for_zero_total():
    assert normalize_weights({"A": 0}) == {"CASH": 100.0}


def test_turnover_zero_for_same_weights():
    assert turnover({"A": 50, "CASH": 50}, {"A": 50, "CASH": 50}) == 0.0


def test_turnover_positive_for_rebalance():
    assert turnover({"A": 100}, {"A": 50, "CASH": 50}) == 0.5


def test_build_rebalance_weights_returns_cash_without_candidates():
    budget = build_risk_budget(MarketRegime("bear", 0.8, 40.0, "bear"))

    weights = build_rebalance_weights([], budget)

    assert weights == {"CASH": 100.0}


def test_build_rebalance_weights_respects_bear_equity_limit():
    budget = build_risk_budget(MarketRegime("bear", 0.8, 40.0, "bear"))
    scores = [
        {"id": "A", "confidence_adjusted_score": 100},
        {"id": "B", "confidence_adjusted_score": 80},
    ]

    weights = build_rebalance_weights(scores, budget)

    invested = sum(weight for asset_id, weight in weights.items() if asset_id != "CASH")
    assert invested <= 40.0
    assert weights["CASH"] >= 60.0


def test_build_rebalance_weights_respects_single_asset_cap():
    budget = build_risk_budget(MarketRegime("bull", 0.8, 90.0, "bull"))
    scores = [{"id": "A", "confidence_adjusted_score": 100}]

    weights = build_rebalance_weights(scores, budget)

    assert weights["A"] <= budget.max_single_asset


def test_calculate_taa_metrics_returns_required_fields():
    metrics = calculate_taa_metrics([1.0, 1.1, 1.05, 1.2], [0.1, -0.045, 0.143], [0.2, 0.1])

    assert {"annual_return", "max_drawdown", "sharpe", "calmar", "turnover", "ending_value"} <= set(metrics)


def test_drawdown_curve_matches_equity_curve_length():
    curve = drawdown_curve([1.0, 1.2, 0.9])

    assert len(curve) == 3
    assert curve[-1] == -25.0


def test_run_taa_backtest_returns_strategy_payload():
    result = run_taa_backtest()

    assert result["strategy"] == "MyInvestTAA"
    assert result["rebalance_frequency"] == "monthly"
    assert result["metrics"]["ending_value"] > 0


def test_run_taa_backtest_returns_chronological_states():
    result = run_taa_backtest()
    dates = [state["date"] for state in result["states"]]

    assert dates == sorted(dates)


def test_run_taa_backtest_weights_sum_to_one_hundred():
    result = run_taa_backtest()

    for state in result["states"]:
        assert round(sum(state["weights"].values()), 4) == 100.0


def test_run_taa_backtest_has_cash_constraint_after_first_rebalance():
    result = run_taa_backtest()

    assert any(state["weights"].get("CASH", 0) >= 10 for state in result["states"][1:])


def test_run_taa_backtest_rejects_non_monthly_frequency():
    with pytest.raises(ValueError):
        run_taa_backtest(rebalance_frequency="daily")


def test_run_taa_backtest_rejects_non_positive_capital():
    with pytest.raises(ValueError):
        run_taa_backtest(initial_capital=0)


def test_run_taa_backtest_rejects_negative_transaction_cost():
    with pytest.raises(ValueError):
        run_taa_backtest(transaction_cost=-0.001)


def test_run_taa_backtest_rejects_invalid_cash_return():
    with pytest.raises(ValueError):
        run_taa_backtest(cash_return=-1.0)


def test_run_taa_backtest_records_assumptions():
    result = run_taa_backtest(transaction_cost=0.001, cash_return=0.015)

    assert result["assumptions"]["transaction_cost"] == 0.001
    assert result["assumptions"]["cash_return"] == 0.015


def test_run_taa_backtest_transaction_cost_lowers_ending_value():
    no_cost = run_taa_backtest(transaction_cost=0.0)
    with_cost = run_taa_backtest(transaction_cost=0.01)

    assert with_cost["metrics"]["ending_value"] <= no_cost["metrics"]["ending_value"]


def test_run_taa_backtest_cash_return_applies_to_cash_weight():
    result = run_taa_backtest(
        assets=[],
        price_history={
            "510300": [
                {"date": "2024-01-31", "close": 1.0},
                {"date": "2024-02-29", "close": 1.0},
            ]
        },
        cash_return=0.12,
    )

    assert result["metrics"]["ending_value"] > 1.0


def test_run_taa_backtest_handles_empty_history():
    result = run_taa_backtest(assets=[], price_history={}, initial_capital=1.0)

    assert result["states"] == []
    assert result["metrics"]["ending_value"] == 1.0


def test_run_taa_backtest_equity_and_drawdown_curves_align():
    result = run_taa_backtest()

    assert len(result["equity_curve"]) == len(result["drawdown_curve"])


def test_run_taa_backtest_records_turnover_metric():
    result = run_taa_backtest()

    assert result["metrics"]["turnover"] >= 0


def test_run_taa_backtest_does_not_create_negative_portfolio_value():
    result = run_taa_backtest()

    assert all(point["value"] > 0 for point in result["equity_curve"])


def test_run_taa_backtest_records_rebalance_signals():
    result = run_taa_backtest()

    assert any(state["signals"].get("scores") for state in result["states"])


def test_run_taa_backtest_records_rebalance_reason():
    result = run_taa_backtest()

    assert any(state["reason"] for state in result["states"])
