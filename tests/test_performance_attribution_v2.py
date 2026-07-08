from engine.performance_attribution import PerformanceAttributionReport, analyze_performance_contribution


def _sample_backtest() -> dict:
    return {
        "strategy": "MyInvestTAA",
        "states": [
            {"date": "2024-01-31", "weights": {"A": 50.0, "B": 30.0, "CASH": 20.0}},
            {"date": "2024-02-29", "weights": {"A": 60.0, "B": 20.0, "CASH": 20.0}},
            {"date": "2024-03-31", "weights": {"A": 40.0, "B": 40.0, "CASH": 20.0}},
        ],
    }


def _sample_history() -> dict[str, list[dict]]:
    return {
        "A": [
            {"date": "2024-01-31", "close": 100.0},
            {"date": "2024-02-29", "close": 110.0},
            {"date": "2024-03-31", "close": 121.0},
        ],
        "B": [
            {"date": "2024-01-31", "close": 200.0},
            {"date": "2024-02-29", "close": 180.0},
            {"date": "2024-03-31", "close": 198.0},
        ],
    }


def test_performance_attribution_report_as_dict():
    report = PerformanceAttributionReport("S", {"A": 1.0}, [{"period": "P"}], [{"asset_id": "A"}])

    payload = report.as_dict()

    assert payload["strategy"] == "S"
    assert payload["asset_contribution"]["A"] == 1.0
    assert payload["periods"][0]["period"] == "P"


def test_analyze_performance_contribution_returns_strategy():
    report = analyze_performance_contribution(_sample_backtest(), _sample_history())

    assert report["strategy"] == "MyInvestTAA"


def test_analyze_performance_contribution_uses_previous_weights():
    report = analyze_performance_contribution(_sample_backtest(), _sample_history())

    first_period = report["periods"][0]["contribution"]

    assert first_period["A"] == 5.0
    assert first_period["B"] == -3.0


def test_analyze_performance_contribution_accumulates_by_asset():
    report = analyze_performance_contribution(_sample_backtest(), _sample_history())

    assert report["asset_contribution"]["A"] == 11.0
    assert report["asset_contribution"]["B"] == -1.0


def test_analyze_performance_contribution_sorts_top_contributors_descending():
    report = analyze_performance_contribution(_sample_backtest(), _sample_history())

    assert report["top_contributors"][0]["asset_id"] == "A"


def test_analyze_performance_contribution_limits_top_contributors_to_five():
    backtest = {
        "strategy": "MyInvestTAA",
        "states": [
            {"date": "2024-01-31", "weights": {f"A{i}": 10.0 for i in range(10)}},
            {"date": "2024-02-29", "weights": {f"A{i}": 10.0 for i in range(10)}},
        ],
    }
    history = {
        f"A{i}": [{"date": "2024-01-31", "close": 1.0}, {"date": "2024-02-29", "close": 1.0 + i / 100.0}]
        for i in range(10)
    }

    report = analyze_performance_contribution(backtest, history)

    assert len(report["top_contributors"]) == 5


def test_analyze_performance_contribution_records_period_labels():
    report = analyze_performance_contribution(_sample_backtest(), _sample_history())

    assert report["periods"][0]["period"] == "2024-01-31:2024-02-29"


def test_analyze_performance_contribution_excludes_cash():
    report = analyze_performance_contribution(_sample_backtest(), _sample_history())

    assert "CASH" not in report["asset_contribution"]


def test_analyze_performance_contribution_handles_missing_history_as_zero():
    history = _sample_history()
    del history["B"]

    report = analyze_performance_contribution(_sample_backtest(), history)

    assert "B" not in report["asset_contribution"]


def test_analyze_performance_contribution_handles_zero_previous_close():
    history = {
        "A": [{"date": "2024-01-31", "close": 0.0}, {"date": "2024-02-29", "close": 1.0}],
    }
    backtest = {
        "strategy": "MyInvestTAA",
        "states": [
            {"date": "2024-01-31", "weights": {"A": 100.0}},
            {"date": "2024-02-29", "weights": {"A": 100.0}},
        ],
    }

    report = analyze_performance_contribution(backtest, history)

    assert report["asset_contribution"] == {}


def test_analyze_performance_contribution_handles_empty_states():
    report = analyze_performance_contribution({"strategy": "MyInvestTAA", "states": []}, _sample_history())

    assert report["periods"] == []
    assert report["asset_contribution"] == {}


def test_analyze_performance_contribution_defaults_to_myinvest_strategy_name():
    report = analyze_performance_contribution({"states": []}, _sample_history())

    assert report["strategy"] == "MyInvestTAA"


def test_analyze_performance_contribution_calculates_second_period():
    report = analyze_performance_contribution(_sample_backtest(), _sample_history())

    second_period = report["periods"][1]["contribution"]

    assert second_period["A"] == 6.0
    assert second_period["B"] == 2.0
