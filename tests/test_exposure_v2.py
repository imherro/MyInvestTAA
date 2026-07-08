import pytest

from engine.exposure.v2 import (
    drawdown_aware_exposure_control,
    optimize_equity_exposure_v2,
    trend_aware_volatility_control,
)


def test_trend_aware_volatility_holds_high_vol_with_positive_trend():
    decision = trend_aware_volatility_control(18.0, 70.0, target_volatility=12.0)

    assert decision.volatility_state == "high_positive_trend"
    assert decision.action == "hold_exposure"
    assert decision.multiplier == 1.0


def test_trend_aware_volatility_reduces_high_vol_with_negative_trend():
    decision = trend_aware_volatility_control(24.0, 35.0, target_volatility=12.0)

    assert decision.volatility_state == "high_negative_trend"
    assert decision.action == "reduce_exposure"
    assert decision.multiplier == 0.70


def test_trend_aware_volatility_trims_high_vol_with_mixed_trend():
    decision = trend_aware_volatility_control(18.0, 50.0, target_volatility=12.0)

    assert decision.volatility_state == "high_mixed_trend"
    assert decision.action == "trim_exposure"
    assert decision.multiplier == 0.90


def test_trend_aware_volatility_adds_low_vol_with_positive_trend():
    decision = trend_aware_volatility_control(8.0, 70.0, target_volatility=12.0)

    assert decision.volatility_state == "low_positive_trend"
    assert decision.action == "add_exposure"
    assert decision.multiplier == 1.05


def test_trend_aware_volatility_handles_missing_volatility():
    decision = trend_aware_volatility_control(0.0, 70.0)

    assert decision.volatility_state == "unknown_volatility"
    assert decision.action == "hold_exposure"


def test_trend_aware_volatility_rejects_invalid_target():
    with pytest.raises(ValueError):
        trend_aware_volatility_control(10.0, 70.0, target_volatility=0.0)


def test_drawdown_aware_control_normal_zone():
    decision = drawdown_aware_exposure_control(-3.0)

    assert decision.drawdown_state == "normal_drawdown"
    assert decision.multiplier == 1.0


def test_drawdown_aware_control_moderate_drawdown():
    decision = drawdown_aware_exposure_control(-6.0)

    assert decision.drawdown_state == "moderate_drawdown"
    assert decision.multiplier == 0.90


def test_drawdown_aware_control_deep_drawdown():
    decision = drawdown_aware_exposure_control(-12.0)

    assert decision.drawdown_state == "deep_drawdown"
    assert decision.multiplier == 0.70


def test_drawdown_aware_control_recovers_moderate_drawdown():
    decision = drawdown_aware_exposure_control(-6.0, previous_drawdown_pct=-8.0)

    assert decision.drawdown_state == "recovering_moderate_drawdown"
    assert decision.multiplier == 1.0
    assert decision.recovering is True


def test_drawdown_aware_control_recovers_deep_drawdown_gradually():
    decision = drawdown_aware_exposure_control(-11.0, previous_drawdown_pct=-13.0)

    assert decision.drawdown_state == "recovering_deep_drawdown"
    assert decision.multiplier == 0.85


def test_drawdown_aware_control_restores_after_small_recovery():
    decision = drawdown_aware_exposure_control(-4.0, previous_drawdown_pct=-6.0)

    assert decision.drawdown_state == "recovering"
    assert decision.multiplier == 1.05


def test_drawdown_aware_control_rejects_positive_thresholds():
    with pytest.raises(ValueError):
        drawdown_aware_exposure_control(-4.0, moderate_drawdown=5.0)


def test_drawdown_aware_control_rejects_inverted_thresholds():
    with pytest.raises(ValueError):
        drawdown_aware_exposure_control(-4.0, moderate_drawdown=-12.0, deep_drawdown=-10.0)


def test_optimize_equity_exposure_v2_returns_required_payload():
    decision = optimize_equity_exposure_v2("bull", 90.0, 12.0, 70.0, -2.0, 0.60)

    payload = decision.as_dict()

    assert {"equity_target", "raw_equity_target", "volatility_control", "drawdown_control"} <= set(payload)


def test_optimize_equity_exposure_v2_holds_high_vol_positive_trend():
    decision = optimize_equity_exposure_v2("bull", 90.0, 18.0, 70.0, -2.0, 0.30)

    assert decision.equity_target == 90.0
    assert decision.volatility_control.volatility_state == "high_positive_trend"


def test_optimize_equity_exposure_v2_reduces_high_vol_negative_trend():
    decision = optimize_equity_exposure_v2("bull", 90.0, 18.0, 35.0, -2.0, 0.60)

    assert decision.equity_target == 63.0
    assert "high volatility with weak trend is risk" in decision.reason


def test_optimize_equity_exposure_v2_penalizes_weak_breadth_only_with_weak_trend():
    decision = optimize_equity_exposure_v2("neutral", 60.0, 12.0, 40.0, -2.0, 0.30)

    assert decision.equity_target == 54.0
    assert "breadth weak only penalized when trend is not supportive" in decision.reason


def test_optimize_equity_exposure_v2_ignores_weak_breadth_with_positive_trend():
    decision = optimize_equity_exposure_v2("bull", 90.0, 12.0, 70.0, -2.0, 0.30)

    assert decision.equity_target == 90.0


def test_optimize_equity_exposure_v2_smooths_monthly_change():
    decision = optimize_equity_exposure_v2(
        "bull",
        90.0,
        8.0,
        70.0,
        -2.0,
        0.60,
        previous_equity_target=50.0,
        monthly_max_change=10.0,
    )

    assert decision.raw_equity_target == 90.0
    assert decision.equity_target == 60.0
    assert "monthly exposure smoothing" in decision.reason


def test_optimize_equity_exposure_v2_rejects_invalid_smoothing():
    with pytest.raises(ValueError):
        optimize_equity_exposure_v2("bull", 90.0, 8.0, 70.0, -2.0, monthly_max_change=0.0)
