from backtest.evaluation import rolling_analysis


def test_rolling_analysis_returns_strategy_name():
    result = rolling_analysis()

    assert result["strategy"] == "MyInvestTAA"


def test_rolling_analysis_returns_default_windows():
    result = rolling_analysis()

    assert {item["rolling_period"] for item in result["windows"]} == {"1Y", "3Y", "5Y"}


def test_rolling_analysis_returns_primary_benchmark():
    result = rolling_analysis()

    assert result["primary_benchmark"] == "HS300_BUY_HOLD"


def test_rolling_analysis_window_contains_benchmark_details():
    result = rolling_analysis()
    first_window = result["windows"][0]

    assert "HS300_BUY_HOLD" in first_window["benchmarks"]


def test_rolling_analysis_win_rate_is_ratio():
    result = rolling_analysis()

    assert 0.0 <= result["rolling_win_rate"] <= 1.0


def test_rolling_analysis_avg_alpha_is_numeric():
    result = rolling_analysis()

    assert isinstance(result["avg_alpha"], float)


def test_rolling_analysis_accepts_custom_windows():
    result = rolling_analysis(windows={"2Y": 2})

    assert len(result["windows"]) == 1
    assert result["windows"][0]["rolling_period"] == "2Y"


def test_rolling_analysis_handles_empty_curves():
    result = rolling_analysis(
        comparison={
            "equity_curves": {"MyInvestTAA": [], "HS300_BUY_HOLD": []},
        }
    )

    assert result["rolling_win_rate"] == 0.0


def test_rolling_analysis_reports_observation_count():
    result = rolling_analysis()
    observations = result["windows"][0]["benchmarks"]["HS300_BUY_HOLD"]["observations"]

    assert observations >= 0


def test_rolling_analysis_reports_drawdown_improvement_rate():
    result = rolling_analysis()
    value = result["windows"][0]["benchmarks"]["HS300_BUY_HOLD"]["positive_drawdown_improvement_rate"]

    assert 0.0 <= value <= 1.0
