import pytest

from engine.exposure import (
    ExposureDecision,
    breadth_control_multiplier,
    clamp_exposure,
    drawdown_control_multiplier,
    optimize_equity_exposure,
    volatility_target_exposure,
)


def test_clamp_exposure_keeps_value_inside_bounds():
    assert clamp_exposure(65.123) == 65.12


def test_clamp_exposure_applies_minimum():
    assert clamp_exposure(10.0) == 20.0


def test_clamp_exposure_applies_maximum():
    assert clamp_exposure(100.0) == 90.0


def test_clamp_exposure_rejects_invalid_bounds():
    with pytest.raises(ValueError):
        clamp_exposure(50.0, minimum=80.0, maximum=40.0)


def test_volatility_target_exposure_reduces_high_volatility():
    assert volatility_target_exposure(60.0, current_volatility=24.0) == 30.0


def test_volatility_target_exposure_raises_low_volatility():
    assert volatility_target_exposure(40.0, current_volatility=6.0) == 80.0


def test_volatility_target_exposure_clamps_to_minimum():
    assert volatility_target_exposure(40.0, current_volatility=60.0) == 20.0


def test_volatility_target_exposure_clamps_to_maximum():
    assert volatility_target_exposure(70.0, current_volatility=4.0) == 90.0


def test_volatility_target_exposure_keeps_base_when_current_volatility_missing():
    assert volatility_target_exposure(55.0, current_volatility=0.0) == 55.0


def test_volatility_target_exposure_rejects_invalid_target():
    with pytest.raises(ValueError):
        volatility_target_exposure(55.0, current_volatility=10.0, target_volatility=0.0)


def test_drawdown_control_multiplier_normal_zone():
    assert drawdown_control_multiplier(-4.99) == 1.0


def test_drawdown_control_multiplier_moderate_drawdown():
    assert drawdown_control_multiplier(-5.0) == 0.80


def test_drawdown_control_multiplier_deep_drawdown():
    assert drawdown_control_multiplier(-10.0) == 0.60


def test_breadth_control_multiplier_ignores_missing_breadth():
    assert breadth_control_multiplier(None) == 1.0


def test_breadth_control_multiplier_penalizes_weak_breadth():
    assert breadth_control_multiplier(0.39) == 0.85


def test_breadth_control_multiplier_penalizes_soft_breadth():
    assert breadth_control_multiplier(0.45) == 0.95


def test_breadth_control_multiplier_keeps_healthy_breadth():
    assert breadth_control_multiplier(0.50) == 1.0


def test_exposure_decision_as_dict_returns_payload():
    decision = ExposureDecision(65.0, 0.72, ["breadth weakening"], "neutral", 12.0, -3.0, 0.45)

    payload = decision.as_dict()

    assert payload == {
        "equity_target": 65.0,
        "confidence": 0.72,
        "reason": ["breadth weakening"],
        "regime": "neutral",
        "volatility": 12.0,
        "drawdown": -3.0,
        "breadth": 0.45,
    }


def test_optimize_equity_exposure_returns_required_fields():
    decision = optimize_equity_exposure("neutral", 65.0, 12.0, -2.0, 0.60)

    payload = decision.as_dict()

    assert {"equity_target", "confidence", "reason", "regime", "volatility", "drawdown", "breadth"} <= set(payload)


def test_optimize_equity_exposure_flags_high_volatility():
    decision = optimize_equity_exposure("neutral", 65.0, 20.0, -2.0, 0.60)

    assert "volatility rising" in decision.reason
    assert decision.equity_target < 65.0


def test_optimize_equity_exposure_flags_contained_volatility():
    decision = optimize_equity_exposure("neutral", 40.0, 6.0, -2.0, 0.60)

    assert "volatility contained" in decision.reason
    assert decision.equity_target > 40.0


def test_optimize_equity_exposure_flags_portfolio_drawdown_control():
    decision = optimize_equity_exposure("neutral", 65.0, 12.0, -7.0, 0.60)

    assert "portfolio drawdown control" in decision.reason
    assert decision.equity_target == 52.0


def test_optimize_equity_exposure_flags_breadth_weakening():
    decision = optimize_equity_exposure("neutral", 65.0, 12.0, -2.0, 0.35)

    assert "breadth weakening" in decision.reason
    assert decision.equity_target == 55.25


def test_optimize_equity_exposure_applies_all_risk_controls_and_floor():
    decision = optimize_equity_exposure("bear", 65.0, 24.0, -12.0, 0.35)

    assert decision.equity_target == 20.0
    assert decision.confidence == 0.35


def test_optimize_equity_exposure_rounds_inputs():
    decision = optimize_equity_exposure("neutral", 65.0, 12.123456, -3.123456, 0.456789)

    assert decision.volatility == 12.1235
    assert decision.drawdown == -3.1235
    assert decision.breadth == 0.4568
