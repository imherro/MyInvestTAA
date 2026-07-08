from engine.performance_attribution.v3 import decompose_excess_return_v3


def _strategy() -> dict:
    return {
        "strategy": "MyInvestTAA",
        "metrics": {"annual_return": 3.0, "max_drawdown": -10.0},
        "states": [
            {"weights": {"A": 50.0, "CASH": 50.0}},
            {"weights": {"A": 70.0, "CASH": 30.0}},
        ],
    }


def test_decompose_excess_return_v3_returns_required_fields():
    report = decompose_excess_return_v3(_strategy(), {"strategy_id": "SAA", "annual_return": 2.0, "max_drawdown": -12.0, "weights": {"A": 60.0, "CASH": 40.0}})

    assert {"allocation", "selection", "timing", "excess_return", "check_sum"} <= set(report)


def test_decompose_excess_return_v3_sums_to_excess():
    report = decompose_excess_return_v3(_strategy(), {"strategy_id": "SAA", "annual_return": 2.0, "max_drawdown": -12.0, "weights": {"A": 60.0, "CASH": 40.0}})

    assert report["check_sum"] == report["excess_return"]


def test_decompose_excess_return_v3_reports_benchmark_id():
    report = decompose_excess_return_v3(_strategy(), {"strategy_id": "SAA", "annual_return": 2.0, "max_drawdown": -12.0, "weights": {"A": 60.0}})

    assert report["benchmark"] == "SAA"


def test_decompose_excess_return_v3_handles_missing_benchmark():
    report = decompose_excess_return_v3(_strategy(), None)

    assert report["benchmark"] == "UNKNOWN"


def test_decompose_excess_return_v3_handles_empty_states():
    strategy = {"strategy": "MyInvestTAA", "metrics": {"annual_return": 1.0, "max_drawdown": -1.0}, "states": []}

    report = decompose_excess_return_v3(strategy, {"strategy_id": "SAA", "annual_return": 0.5, "max_drawdown": -2.0, "weights": {}})

    assert "timing" in report


def test_decompose_excess_return_v3_uses_exposure_gap():
    high_exposure = _strategy()
    high_exposure["states"] = [{"weights": {"A": 100.0}}, {"weights": {"A": 100.0}}]

    report = decompose_excess_return_v3(high_exposure, {"strategy_id": "SAA", "annual_return": 2.0, "max_drawdown": -12.0, "weights": {"A": 60.0}})

    assert report["timing"] > 0


def test_decompose_excess_return_v3_allocation_reflects_drawdown_improvement():
    report = decompose_excess_return_v3(_strategy(), {"strategy_id": "SAA", "annual_return": 2.0, "max_drawdown": -20.0, "weights": {"A": 60.0}})

    assert report["allocation"] > 0


def test_decompose_excess_return_v3_allocation_penalizes_worse_drawdown():
    strategy = _strategy()
    strategy["metrics"]["max_drawdown"] = -25.0

    report = decompose_excess_return_v3(strategy, {"strategy_id": "SAA", "annual_return": 2.0, "max_drawdown": -10.0, "weights": {"A": 60.0}})

    assert report["allocation"] < 0


def test_decompose_excess_return_v3_excludes_cash_from_benchmark_exposure():
    strategy = _strategy()
    strategy["states"] = [{"weights": {"A": 70.0, "CASH": 30.0}}]

    report = decompose_excess_return_v3(strategy, {"strategy_id": "SAA", "annual_return": 2.0, "max_drawdown": -12.0, "weights": {"A": 70.0, "CASH": 30.0}})

    assert report["timing"] == 0.0


def test_decompose_excess_return_v3_keeps_interaction_zero_for_auditability():
    report = decompose_excess_return_v3(_strategy(), {"strategy_id": "SAA", "annual_return": 2.0, "max_drawdown": -12.0, "weights": {"A": 60.0}})

    assert report["interaction"] == 0.0
