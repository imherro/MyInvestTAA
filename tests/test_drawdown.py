from engine.drawdown import calculate_drawdown, drawdown_score


def test_calculate_drawdown_handles_peak_decline_and_partial_recovery():
    metrics = calculate_drawdown([100, 120, 90, 96])

    assert metrics.current_drawdown_pct == -20.0
    assert metrics.max_drawdown_pct == -25.0
    assert metrics.drawdown_percentile == 0.8
    assert metrics.pressure_zone == "high"
    assert drawdown_score(metrics) == 80.0


def test_calculate_drawdown_returns_zero_for_constant_high():
    metrics = calculate_drawdown([100, 105, 110])

    assert metrics.current_drawdown_pct == 0.0
    assert metrics.max_drawdown_pct == 0.0
    assert metrics.drawdown_percentile == 0.0
    assert metrics.pressure_zone == "normal"

