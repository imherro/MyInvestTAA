import pytest

from backtest.benchmark import (
    BenchmarkResult,
    BenchmarkStrategy,
    calculate_alpha_metrics,
    compare_strategies,
    run_buy_hold_backtest,
    run_classic_saa_backtest,
    run_equal_weight_backtest,
    run_fixed_weight_backtest,
)
from backtest.benchmark.models import normalize_benchmark_weights


SAMPLE_ASSETS = [
    {"id": "510300", "name": "沪深300ETF", "anchor_score": 65},
    {"id": "512890", "name": "红利低波ETF", "anchor_score": 85},
    {"id": "511010", "name": "国债ETF", "anchor_score": 80},
    {"id": "518880", "name": "黄金ETF", "anchor_score": 70},
]

SAMPLE_HISTORY = {
    "510300": [
        {"date": "2024-01-31", "close": 1.0},
        {"date": "2024-02-29", "close": 1.1},
        {"date": "2024-03-31", "close": 0.99},
        {"date": "2024-04-30", "close": 1.05},
    ],
    "512890": [
        {"date": "2024-01-31", "close": 1.0},
        {"date": "2024-02-29", "close": 1.02},
        {"date": "2024-03-31", "close": 1.01},
        {"date": "2024-04-30", "close": 1.04},
    ],
    "511010": [
        {"date": "2024-01-31", "close": 1.0},
        {"date": "2024-02-29", "close": 1.01},
        {"date": "2024-03-31", "close": 1.02},
        {"date": "2024-04-30", "close": 1.03},
    ],
    "518880": [
        {"date": "2024-01-31", "close": 1.0},
        {"date": "2024-02-29", "close": 1.06},
        {"date": "2024-03-31", "close": 1.02},
        {"date": "2024-04-30", "close": 1.08},
    ],
}


def test_normalize_benchmark_weights_sums_to_one_hundred():
    weights = normalize_benchmark_weights({"A": 2, "B": 1})

    assert round(sum(weights.values()), 4) == 100.0


def test_normalize_benchmark_weights_empty_returns_cash():
    assert normalize_benchmark_weights({}) == {"CASH": 100.0}


def test_normalize_benchmark_weights_zero_total_returns_cash():
    assert normalize_benchmark_weights({"A": 0}) == {"CASH": 100.0}


def test_normalize_benchmark_weights_rejects_negative_weight():
    with pytest.raises(ValueError):
        normalize_benchmark_weights({"A": 100, "B": -1})


def test_benchmark_strategy_as_dict_contains_description():
    strategy = BenchmarkStrategy("TEST", "Test Strategy", {"A": 100.0}, "desc")

    payload = strategy.as_dict()

    assert payload["strategy_id"] == "TEST"
    assert payload["description"] == "desc"


def test_benchmark_result_as_dict_contains_curves():
    strategy = BenchmarkStrategy("TEST", "Test Strategy", {"A": 100.0}, "desc")
    result = BenchmarkResult(strategy, None, {"annual_return": 0}, [], [])

    payload = result.as_dict()

    assert payload["name"] == "Test Strategy"
    assert "equity_curve" in payload
    assert "drawdown_curve" in payload


def test_buy_hold_backtest_returns_hs300_strategy_id():
    result = run_buy_hold_backtest(assets=SAMPLE_ASSETS, price_history=SAMPLE_HISTORY)

    assert result["strategy_id"] == "HS300_BUY_HOLD"
    assert result["weights"] == {"510300": 100.0}


def test_buy_hold_backtest_returns_required_metrics():
    result = run_buy_hold_backtest(assets=SAMPLE_ASSETS, price_history=SAMPLE_HISTORY)

    assert {"annual_return", "max_drawdown", "sharpe", "ending_value"} <= set(result["metrics"])


def test_buy_hold_backtest_equity_curve_matches_period_rows():
    result = run_buy_hold_backtest(assets=SAMPLE_ASSETS, price_history=SAMPLE_HISTORY)

    assert len(result["equity_curve"]) == result["period"]["rows"]


def test_buy_hold_backtest_rejects_unknown_asset():
    with pytest.raises(ValueError):
        run_buy_hold_backtest("UNKNOWN", assets=SAMPLE_ASSETS, price_history=SAMPLE_HISTORY)


def test_buy_hold_backtest_rejects_missing_history():
    with pytest.raises(ValueError):
        run_buy_hold_backtest(assets=SAMPLE_ASSETS, price_history={})


def test_buy_hold_backtest_handles_empty_history():
    result = run_buy_hold_backtest(
        assets=SAMPLE_ASSETS,
        price_history={"510300": []},
    )

    assert result["period"] is None
    assert result["metrics"]["ending_value"] == 1.0


def test_fixed_weight_backtest_includes_cash_weight():
    result = run_fixed_weight_backtest(
        assets=SAMPLE_ASSETS,
        price_history=SAMPLE_HISTORY,
    )

    assert result["weights"]["510300"] == 60.0
    assert result["weights"]["CASH"] == 40.0


def test_fixed_weight_backtest_cash_return_affects_flat_asset():
    flat_history = {
        "510300": [
            {"date": "2024-01-31", "close": 1.0},
            {"date": "2024-02-29", "close": 1.0},
            {"date": "2024-03-31", "close": 1.0},
        ]
    }

    no_cash_yield = run_fixed_weight_backtest(
        assets=SAMPLE_ASSETS,
        price_history=flat_history,
        cash_annual_return=0.0,
    )
    cash_yield = run_fixed_weight_backtest(
        assets=SAMPLE_ASSETS,
        price_history=flat_history,
        cash_annual_return=0.12,
    )

    assert cash_yield["metrics"]["ending_value"] > no_cash_yield["metrics"]["ending_value"]


def test_fixed_weight_backtest_rejects_non_positive_initial_capital():
    with pytest.raises(ValueError):
        run_fixed_weight_backtest(
            assets=SAMPLE_ASSETS,
            price_history=SAMPLE_HISTORY,
            initial_capital=0,
        )


def test_equal_weight_backtest_uses_all_assets_by_default():
    result = run_equal_weight_backtest(assets=SAMPLE_ASSETS, price_history=SAMPLE_HISTORY)

    assert set(result["weights"]) == {"510300", "512890", "511010", "518880"}
    assert round(sum(result["weights"].values()), 4) == 100.0


def test_equal_weight_backtest_accepts_subset():
    result = run_equal_weight_backtest(
        asset_ids=["512890"],
        assets=SAMPLE_ASSETS,
        price_history=SAMPLE_HISTORY,
    )

    assert result["weights"] == {"512890": 100.0}


def test_equal_weight_backtest_empty_asset_ids_returns_cash_result():
    result = run_equal_weight_backtest(
        asset_ids=[],
        assets=SAMPLE_ASSETS,
        price_history=SAMPLE_HISTORY,
    )

    assert result["weights"] == {"CASH": 100.0}
    assert result["period"] is None


def test_equal_weight_backtest_rejects_unknown_asset():
    with pytest.raises(ValueError):
        run_equal_weight_backtest(
            asset_ids=["UNKNOWN"],
            assets=SAMPLE_ASSETS,
            price_history=SAMPLE_HISTORY,
        )


def test_calculate_alpha_metrics_returns_excess_return():
    alpha = calculate_alpha_metrics(
        {"annual_return": 8, "max_drawdown": -10, "sharpe": 1.0, "ending_value": 1.2},
        {"annual_return": 5, "max_drawdown": -12, "sharpe": 0.7, "ending_value": 1.1},
    )

    assert alpha["excess_return"] == 3
    assert alpha["sharpe_difference"] == 0.3


def test_calculate_alpha_metrics_reports_drawdown_improvement():
    alpha = calculate_alpha_metrics(
        {"annual_return": 8, "max_drawdown": -8, "sharpe": 1.0, "ending_value": 1.2},
        {"annual_return": 5, "max_drawdown": -12, "sharpe": 0.7, "ending_value": 1.1},
    )

    assert alpha["drawdown_improvement"] == 4


def test_classic_saa_backtest_uses_equity_bond_gold_weights():
    result = run_classic_saa_backtest(assets=SAMPLE_ASSETS, price_history=SAMPLE_HISTORY)

    assert result["strategy_id"] == "SAA_CLASSIC"
    assert result["weights"] == {"510300": 60.0, "511010": 30.0, "518880": 10.0}


def test_classic_saa_backtest_returns_metrics():
    result = run_classic_saa_backtest(assets=SAMPLE_ASSETS, price_history=SAMPLE_HISTORY)

    assert result["metrics"]["ending_value"] > 0


def test_classic_saa_backtest_rejects_missing_bond_asset():
    with pytest.raises(ValueError):
        run_classic_saa_backtest(
            assets=[{"id": "510300", "name": "沪深300ETF"}, {"id": "518880", "name": "黄金ETF"}],
            price_history=SAMPLE_HISTORY,
        )


def test_compare_strategies_returns_five_rows():
    result = compare_strategies()

    assert len(result["rows"]) == 5


def test_compare_strategies_contains_required_strategy_fields():
    result = compare_strategies()
    row = result["rows"][0]

    assert {"annual_return", "max_drawdown", "sharpe", "excess_return"} <= set(row)


def test_compare_strategies_includes_default_benchmarks():
    result = compare_strategies()

    assert {"HS300_BUY_HOLD", "SAA_60_40", "SAA_CLASSIC", "EQUAL_WEIGHT"} <= set(result["strategies"])


def test_compare_strategies_returns_equity_curves_for_each_strategy():
    result = compare_strategies()

    assert set(result["equity_curves"]) == set(result["strategies"])
