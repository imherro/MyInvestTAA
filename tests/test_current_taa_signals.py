from datetime import date, timedelta

import pytest

from current_taa.model import ModelConfig, compute_score


def _rows(count=253, growth=0.001):
    start = date(2020, 1, 1)
    return [
        {"date": (start + timedelta(days=index)).isoformat(), "close": 100 * (1 + growth) ** index}
        for index in range(count)
    ]


def test_score_uses_6m_12m_and_drawdown_resilience():
    rows = _rows()
    result = compute_score(rows, rows[-1]["date"])
    momentum_6m = rows[-1]["close"] / rows[-127]["close"] - 1
    momentum_12m = rows[-1]["close"] / rows[0]["close"] - 1
    assert result["momentum_6m"] == pytest.approx(momentum_6m, abs=1e-8)
    assert result["momentum_12m"] == pytest.approx(momentum_12m, abs=1e-8)
    assert result["drawdown_resilience"] == 1.0
    assert result["score"] == pytest.approx(0.4 * momentum_6m + 0.3 * momentum_12m + 0.3, abs=1e-8)


def test_score_does_not_read_future_rows():
    rows = _rows(260)
    signal_date = rows[252]["date"]
    before = compute_score(rows, signal_date)
    rows[-1]["close"] *= 100
    assert compute_score(rows, signal_date) == before


def test_score_requires_complete_12m_history():
    rows = _rows(252)
    assert compute_score(rows, rows[-1]["date"]) is None


def test_score_requires_a_price_on_signal_date():
    rows = _rows()
    assert compute_score(rows, (date.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).isoformat()) is None


def test_model_weights_are_fixed_by_contract():
    config = ModelConfig()
    assert (config.momentum_6m_weight, config.momentum_12m_weight, config.drawdown_resilience_weight) == (0.4, 0.3, 0.3)
