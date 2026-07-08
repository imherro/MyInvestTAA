import pytest

from backtest.taa import run_taa_backtest
from backtest.taa.engine import (
    _apply_volatility_adjustment,
    _smooth_weight_transition,
    _trend_score,
    _volatility,
)


def _history(values: list[float]) -> list[dict]:
    return [
        {"date": f"2024-{index + 1:02d}-28", "close": value}
        for index, value in enumerate(values)
    ]


def test_trend_score_rewards_uptrend():
    assert _trend_score(_history([1.0, 1.05, 1.1, 1.2, 1.3, 1.4])) > 50


def test_trend_score_is_zero_for_short_history():
    assert _trend_score(_history([1.0, 1.1])) == 0.0


def test_volatility_returns_positive_value():
    assert _volatility(_history([1.0, 1.1, 1.0, 1.2])) > 0


def test_volatility_adjustment_boosts_low_volatility_score():
    adjusted = _apply_volatility_adjustment(
        [
            {"id": "LOW", "confidence_adjusted_score": 10.0, "volatility": 0.02},
            {"id": "HIGH", "confidence_adjusted_score": 10.0, "volatility": 0.20},
        ]
    )

    assert adjusted[0]["id"] == "LOW"


def test_smooth_weight_transition_limits_single_period_change():
    result = _smooth_weight_transition({"CASH": 100.0}, {"A": 70.0, "CASH": 30.0}, 10.0)

    assert result["A"] == 10.0
    assert round(sum(result.values()), 4) == 100.0


def test_smooth_weight_transition_returns_cash_for_empty_total():
    assert _smooth_weight_transition({"A": 0.0}, {"A": 0.0}, 10.0) == {"CASH": 100.0}


def test_run_taa_backtest_accepts_score_version_v4():
    result = run_taa_backtest(score_version="v4")

    assert result["assumptions"]["score_version"] == "v4"


def test_run_taa_backtest_rejects_unknown_score_version():
    with pytest.raises(ValueError):
        run_taa_backtest(score_version="bad")


def test_run_taa_backtest_records_max_weight_step():
    result = run_taa_backtest(max_weight_step=10.0)

    assert result["assumptions"]["max_weight_step"] == 10.0


def test_run_taa_backtest_rejects_non_positive_max_weight_step():
    with pytest.raises(ValueError):
        run_taa_backtest(max_weight_step=0)


def test_run_taa_backtest_records_volatility_adjustment():
    result = run_taa_backtest(volatility_adjustment=True)

    assert result["assumptions"]["volatility_adjustment"] is True


def test_run_taa_backtest_v4_scores_include_trend_and_volatility():
    result = run_taa_backtest(score_version="v4", volatility_adjustment=True)
    scores = next(state["signals"]["scores"] for state in result["states"] if state["signals"].get("scores"))

    assert {"trend_score", "volatility"} <= set(scores[0])


def test_run_taa_backtest_records_target_weights_when_smoothing():
    result = run_taa_backtest(max_weight_step=10.0)

    assert any("target_weights" in state["signals"] for state in result["states"][1:])
