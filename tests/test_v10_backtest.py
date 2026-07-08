import pytest

from backtest.taa import run_taa_backtest


def _history(values: list[float]) -> list[dict]:
    return [
        {"date": f"2024-{index + 1:02d}-28", "close": value}
        for index, value in enumerate(values)
    ]


def _first_v10_state(result: dict) -> dict:
    return next(state for state in result["states"] if state["signals"].get("exposure_decision"))


def test_run_taa_backtest_accepts_score_version_v10():
    result = run_taa_backtest(score_version="v10")

    assert result["assumptions"]["score_version"] == "v10"


def test_v10_records_robust_exposure_config():
    result = run_taa_backtest(score_version="v10", robust_exposure_config={"target_volatility": 15.0})

    assert result["assumptions"]["robust_exposure_config"] == {"target_volatility": 15.0}


def test_v10_records_exposure_v2_payload():
    result = run_taa_backtest(score_version="v10")
    decision = _first_v10_state(result)["signals"]["exposure_decision"]

    assert {"volatility_control", "drawdown_control", "raw_equity_target", "monthly_max_change"} <= set(decision)


def test_v10_exposure_target_stays_inside_policy_bounds():
    result = run_taa_backtest(score_version="v10")
    decision = _first_v10_state(result)["signals"]["exposure_decision"]

    assert 20.0 <= decision["equity_target"] <= 90.0


def test_v10_risk_budget_uses_exposure_target():
    result = run_taa_backtest(score_version="v10")
    state = _first_v10_state(result)

    assert state["signals"]["risk_budget"]["equity_limit"] == state["signals"]["exposure_decision"]["equity_target"]


def test_v10_records_adaptive_factor_weights():
    result = run_taa_backtest(score_version="v10")
    state = _first_v10_state(result)

    assert state["signals"]["adaptive_factor_weights"]["weights"]


def test_v10_scores_keep_stock_breadth_and_adaptive_fields():
    result = run_taa_backtest(score_version="v10")
    state = _first_v10_state(result)

    assert {"adaptive_regime", "adaptive_reason", "stock_breadth_score"} <= set(state["signals"]["scores"][0])


def test_v10_records_stock_breadth_asset_count():
    result = run_taa_backtest(score_version="v10", stock_price_history={"688981.SH": _history([1.0, 1.1])})

    assert result["assumptions"]["stock_breadth_assets"] == 1


def test_v10_monthly_exposure_smoothing_limits_target_change():
    result = run_taa_backtest(score_version="v10", robust_exposure_config={"monthly_max_change": 5.0})
    targets = [
        state["signals"]["exposure_decision"]["equity_target"]
        for state in result["states"]
        if state["signals"].get("exposure_decision")
    ]

    assert all(abs(current - previous) <= 5.0 for previous, current in zip(targets, targets[1:]))


def test_v10_empty_result_records_robust_config():
    result = run_taa_backtest(
        assets=[],
        price_history={},
        score_version="v10",
        robust_exposure_config={"monthly_max_change": 5.0},
    )

    assert result["assumptions"]["robust_exposure_config"] == {"monthly_max_change": 5.0}


def test_run_taa_backtest_error_mentions_v10_for_unknown_score_version():
    with pytest.raises(ValueError, match="v10"):
        run_taa_backtest(score_version="bad")
