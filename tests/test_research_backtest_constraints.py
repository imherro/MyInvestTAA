from dataclasses import replace

import pytest

from backtest.research.constraints import build_constraint_diagnostics
from backtest.research.data_loader import build_mock_research_price_dataset
from backtest.research.engine import run_research_backtest
from backtest.research.models import ResearchBacktestConfig
from backtest.research.universe import load_research_backtest_universe


ASSETS = load_research_backtest_universe()
CONFIG = ResearchBacktestConfig()
REPORT = run_research_backtest(ASSETS, build_mock_research_price_dataset(ASSETS, periods=520))


def test_constraint_diagnostics_has_no_violations_for_standard_report():
    assert REPORT["constraint_diagnostics"]["violations"] == []


def test_constraint_diagnostics_reports_cash_drag():
    cash_drag = REPORT["constraint_diagnostics"]["cash_drag"]

    assert {"average_cash", "max_cash", "months_cash_above_30"} == set(cash_drag)
    assert 0.0 <= cash_drag["average_cash"] <= cash_drag["max_cash"] <= 1.0


def test_constraint_diagnostics_reports_cap_hits():
    assert set(REPORT["constraint_diagnostics"]["cap_hits"]) == {
        "single_asset_cap",
        "theme_sleeve_cap",
        "single_theme_cap",
    }


def test_constraint_diagnostics_detects_single_asset_violation():
    diagnostics = build_constraint_diagnostics(
        [{"date": "2026-01-01", "weights": {ASSETS[0].asset_id: 0.30}}], ASSETS, CONFIG
    )

    assert diagnostics["violations"][0]["constraint"] == "single_asset_max"


def test_constraint_diagnostics_detects_single_theme_violation():
    theme = next(asset for asset in ASSETS if asset.category == "theme")
    diagnostics = build_constraint_diagnostics(
        [{"date": "2026-01-01", "weights": {theme.asset_id: 0.15}}], ASSETS, CONFIG
    )

    assert {row["constraint"] for row in diagnostics["violations"]} == {"single_theme_max"}


def test_constraint_diagnostics_detects_theme_sleeve_violation():
    themes = [asset for asset in ASSETS if asset.category == "theme"][:2]
    diagnostics = build_constraint_diagnostics(
        [{"date": "2026-01-01", "weights": {themes[0].asset_id: 0.15, themes[1].asset_id: 0.15}}], ASSETS, CONFIG
    )

    assert "theme_sleeve_max" in {row["constraint"] for row in diagnostics["violations"]}


@pytest.mark.parametrize("allocation", REPORT["monthly_allocations"])
def test_all_research_allocations_keep_total_weight_bounded(allocation):
    assert sum(allocation["weights"].values()) <= 1.000001


@pytest.mark.parametrize("allocation", REPORT["monthly_allocations"])
def test_all_research_allocations_obey_single_asset_cap(allocation):
    assert all(weight <= CONFIG.single_asset_max + 1e-8 for asset_id, weight in allocation["weights"].items() if asset_id != "CASH")


@pytest.mark.parametrize("allocation", REPORT["monthly_allocations"])
def test_all_research_allocations_have_nonnegative_cash(allocation):
    assert allocation["weights"].get("CASH", 0.0) >= 0.0


def test_execution_validation_decision_is_a_research_gate_only():
    decision = REPORT["decision"]

    assert decision["ready_for_execution_backtest"] is True
    assert "not production approval" in decision["warning"]


def test_execution_validation_decision_fails_for_weak_sharpe():
    weak = dict(REPORT)
    weak["metrics"] = {**REPORT["metrics"], "sharpe": 0.1}
    from backtest.research.engine import _build_execution_validation_decision

    decision = _build_execution_validation_decision(weak)

    assert decision["ready_for_execution_backtest"] is False
    assert "Sharpe is not above 0.4" in decision["reasons"]
