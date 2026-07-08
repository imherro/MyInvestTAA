from backtest.metrics import max_drawdown, sharpe_ratio
from backtest.simulator import run_sample_backtest, simulate_weighted_buy_hold


def test_max_drawdown_for_equity_curve():
    assert max_drawdown([1.0, 1.2, 0.9, 1.1]) == -25.0


def test_sharpe_ratio_zero_when_returns_do_not_vary():
    assert sharpe_ratio([0.01, 0.01, 0.01]) == 0.0


def test_simulate_weighted_buy_hold_returns_metrics():
    result = simulate_weighted_buy_hold(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 110},
            {"date": "2024-03-01", "close": 99},
        ],
        weight=0.5,
    )

    assert result["period"]["rows"] == 3
    assert "annual_return" in result
    assert "max_drawdown" in result
    assert "sharpe" in result


def test_run_sample_backtest_uses_sample_asset():
    result = run_sample_backtest("512890", weight=0.6)

    assert result["asset_id"] == "512890"
    assert result["asset_name"] == "红利低波ETF"
    assert result["period"]["rows"] >= 10

