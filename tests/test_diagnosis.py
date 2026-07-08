from engine.diagnosis import analyze_regime_effects, compare_strategy_versions, decompose_vs_static


def _backtest_result() -> dict:
    return {
        "strategy": "MyInvestTAA",
        "metrics": {"annual_return": 1.0, "max_drawdown": -10.0, "sharpe": 0.2, "calmar": 0.1, "ending_value": 1.1},
        "states": [
            {"date": "2024-01-31", "portfolio_value": 1.0, "weights": {"CASH": 50.0}, "regime": {"state": "bull"}},
            {"date": "2024-02-29", "portfolio_value": 1.1, "weights": {"CASH": 30.0}, "regime": {"state": "bull"}},
            {"date": "2024-03-31", "portfolio_value": 1.0, "weights": {"CASH": 70.0}, "regime": {"state": "bear"}},
        ],
    }


def test_analyze_regime_effects_returns_regime_rows():
    report = analyze_regime_effects(_backtest_result())

    assert report["regimes"]


def test_analyze_regime_effects_counts_periods():
    report = analyze_regime_effects(_backtest_result())

    assert sum(item["periods"] for item in report["regimes"]) == 2


def test_analyze_regime_effects_reports_worst_regime():
    report = analyze_regime_effects(_backtest_result())

    assert report["worst_regime"] in {"bull", "bear"}


def test_analyze_regime_effects_reports_average_exposure():
    report = analyze_regime_effects(_backtest_result())

    assert "avg_equity_exposure" in report["regimes"][0]


def test_decompose_vs_static_returns_gap_metrics():
    report = decompose_vs_static(_backtest_result(), {"strategy_id": "SAA_60_40", "annual_return": 2.0, "max_drawdown": -15.0})

    assert report["return_gap"] == -1.0
    assert report["drawdown_improvement"] == 5.0


def test_decompose_vs_static_reports_market_exposure_gap():
    report = decompose_vs_static(_backtest_result(), {"strategy_id": "SAA_60_40", "annual_return": 2.0, "max_drawdown": -15.0})

    assert "market_exposure_gap" in report


def test_decompose_vs_static_handles_missing_benchmark():
    report = decompose_vs_static(_backtest_result(), None)

    assert report["benchmark"] == "UNKNOWN"


def test_compare_strategy_versions_returns_rows():
    report = compare_strategy_versions({"V1": _backtest_result(), "V2": _backtest_result()})

    assert len(report["rows"]) == 2


def test_compare_strategy_versions_selects_best_by_sharpe():
    strong = _backtest_result()
    strong["metrics"] = {**strong["metrics"], "sharpe": 0.5}

    report = compare_strategy_versions({"V1": _backtest_result(), "V2": strong})

    assert report["best_version"] == "V2"


def test_compare_strategy_versions_handles_empty_input():
    report = compare_strategy_versions({})

    assert report["best_version"] is None


def test_decompose_vs_static_splits_return_gap():
    report = decompose_vs_static(_backtest_result(), {"strategy_id": "SAA_60_40", "annual_return": 2.0, "max_drawdown": -15.0})

    assert round(report["timing_contribution"] + report["selection_contribution"], 4) == report["return_gap"]


def test_analyze_regime_effects_handles_empty_states():
    report = analyze_regime_effects({"states": []})

    assert report["regimes"] == []
    assert report["worst_regime"] is None
