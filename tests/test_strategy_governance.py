from engine.governance import StrategyRegistry, StrategyRegistryEntry, build_strategy_registry


def _rows() -> list[dict]:
    return [
        {"version": "V1_CURRENT", "annual_return": 1.0, "max_drawdown": -20.0, "sharpe": 0.1, "calmar": 0.05},
        {"version": "V3_TREND_RISK_ADJUSTED", "annual_return": 3.0, "max_drawdown": -14.0, "sharpe": 0.4, "calmar": 0.2},
        {"version": "V5_RELATIVE_STRENGTH_SELECTION", "annual_return": 4.0, "max_drawdown": -15.0, "sharpe": 0.5, "calmar": 0.25},
    ]


def test_strategy_registry_entry_as_dict_contains_version_status_metrics():
    entry = StrategyRegistryEntry("V3", "production_candidate", {"sharpe": 0.4})

    assert entry.as_dict() == {"version": "V3", "status": "production_candidate", "metrics": {"sharpe": 0.4}}


def test_strategy_registry_as_dict_contains_rows():
    registry = StrategyRegistry("V3", [StrategyRegistryEntry("V3", "production_candidate", {})])

    assert registry.as_dict()["rows"][0]["version"] == "V3"


def test_build_strategy_registry_marks_v3_as_production_candidate():
    registry = build_strategy_registry(_rows())

    v3 = next(row for row in registry["rows"] if row["version"] == "V3_TREND_RISK_ADJUSTED")
    assert v3["status"] == "production_candidate"


def test_build_strategy_registry_marks_v5_as_testing():
    registry = build_strategy_registry(_rows())

    v5 = next(row for row in registry["rows"] if row["version"] == "V5_RELATIVE_STRENGTH_SELECTION")
    assert v5["status"] == "testing"


def test_build_strategy_registry_archives_v1():
    registry = build_strategy_registry(_rows())

    v1 = next(row for row in registry["rows"] if row["version"] == "V1_CURRENT")
    assert v1["status"] == "archive"


def test_build_strategy_registry_reports_production_candidate():
    registry = build_strategy_registry(_rows())

    assert registry["production_candidate"] == "V3_TREND_RISK_ADJUSTED"


def test_build_strategy_registry_preserves_annual_return():
    registry = build_strategy_registry(_rows())

    v5 = next(row for row in registry["rows"] if row["version"] == "V5_RELATIVE_STRENGTH_SELECTION")
    assert v5["metrics"]["annual_return"] == 4.0


def test_build_strategy_registry_preserves_drawdown():
    registry = build_strategy_registry(_rows())

    v3 = next(row for row in registry["rows"] if row["version"] == "V3_TREND_RISK_ADJUSTED")
    assert v3["metrics"]["max_drawdown"] == -14.0


def test_build_strategy_registry_handles_empty_rows():
    registry = build_strategy_registry([])

    assert registry["rows"] == []
    assert registry["production_candidate"] is None


def test_build_strategy_registry_archives_unknown_versions():
    registry = build_strategy_registry([{"version": "EXPERIMENT"}])

    assert registry["rows"][0]["status"] == "archive"


def test_build_strategy_registry_keeps_row_count():
    registry = build_strategy_registry(_rows())

    assert len(registry["rows"]) == 3


def test_build_strategy_registry_includes_calmar_metric():
    registry = build_strategy_registry(_rows())

    assert "calmar" in registry["rows"][0]["metrics"]
