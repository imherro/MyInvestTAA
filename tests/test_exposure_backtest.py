from backtest.taa import run_taa_backtest
from backtest.taa.engine import (
    _annualized_volatility_pct,
    _current_portfolio_drawdown_pct,
    _estimate_current_breadth,
    _risk_budget_from_exposure,
)
from engine.risk.models import RiskBudget


def _history(values: list[float]) -> list[dict]:
    return [
        {"date": f"2024-{index + 1:02d}-28", "close": value}
        for index, value in enumerate(values)
    ]


def _first_v9_state(result: dict) -> dict:
    return next(state for state in result["states"] if state["signals"].get("exposure_decision"))


def test_run_taa_backtest_accepts_score_version_v9():
    result = run_taa_backtest(score_version="v9")

    assert result["assumptions"]["score_version"] == "v9"


def test_v9_records_exposure_decision_payload():
    result = run_taa_backtest(score_version="v9")
    decision = _first_v9_state(result)["signals"]["exposure_decision"]

    assert {"equity_target", "confidence", "reason", "volatility", "drawdown", "breadth"} <= set(decision)


def test_v9_exposure_target_stays_inside_policy_bounds():
    result = run_taa_backtest(score_version="v9")
    decision = _first_v9_state(result)["signals"]["exposure_decision"]

    assert 20.0 <= decision["equity_target"] <= 90.0


def test_v9_risk_budget_uses_exposure_target():
    result = run_taa_backtest(score_version="v9")
    state = _first_v9_state(result)

    assert state["signals"]["risk_budget"]["equity_limit"] == state["signals"]["exposure_decision"]["equity_target"]


def test_v9_records_adaptive_factor_weights():
    result = run_taa_backtest(score_version="v9")
    state = _first_v9_state(result)

    assert state["signals"]["adaptive_factor_weights"]["weights"]


def test_v9_scores_keep_adaptive_regime_fields():
    result = run_taa_backtest(score_version="v9")
    state = _first_v9_state(result)

    assert {"adaptive_regime", "adaptive_reason", "stock_breadth_score"} <= set(state["signals"]["scores"][0])


def test_v9_records_stock_breadth_asset_count():
    result = run_taa_backtest(score_version="v9", stock_price_history={"688981.SH": _history([1.0, 1.1])})

    assert result["assumptions"]["stock_breadth_assets"] == 1


def test_annualized_volatility_pct_returns_zero_for_flat_history():
    assert _annualized_volatility_pct(_history([1.0, 1.0, 1.0])) == 0.0


def test_annualized_volatility_pct_returns_positive_for_variable_history():
    assert _annualized_volatility_pct(_history([1.0, 1.1, 0.9, 1.2])) > 0.0


def test_current_portfolio_drawdown_pct_handles_empty_curve():
    assert _current_portfolio_drawdown_pct([]) == 0.0


def test_current_portfolio_drawdown_pct_uses_latest_value_vs_peak():
    assert _current_portfolio_drawdown_pct([1.0, 1.25, 1.0]) == -20.0


def test_estimate_current_breadth_returns_none_without_observations():
    assert _estimate_current_breadth({"A": [{"date": "2024-01-31", "close": 1.0}]}) is None


def test_estimate_current_breadth_counts_positive_assets():
    histories = {
        "A": _history([1.0, 1.1]),
        "B": _history([1.0, 0.9]),
        "C": _history([1.0, 1.2]),
    }

    assert _estimate_current_breadth(histories) == 0.6667


def test_risk_budget_from_exposure_updates_equity_and_cash_limits():
    budget = RiskBudget("neutral", 65.0, 35.0, 30.0, "base")

    result = _risk_budget_from_exposure(budget, 52.5)

    assert result.equity_limit == 52.5
    assert result.min_cash == 47.5
    assert result.max_single_asset == 30.0
