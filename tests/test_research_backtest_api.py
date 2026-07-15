from pathlib import Path

from fastapi.testclient import TestClient

import backtest.research.report as research_report
from backtest.research.report import write_research_backtest_report
from backend.main import app


client = TestClient(app)


def _sample_report():
    return {
        "available": True,
        "strategy": "RESEARCH_TAA_MVP",
        "universe_count": 13,
        "period": {"start": "2021-01-14", "end": "2026-07-08"},
        "metrics": {"annual_return": 0.1, "max_drawdown": -0.2, "sharpe": 1.0, "calmar": 0.5},
        "equity_curve": [{"date": "2026-07-08", "value": 1.2}],
        "monthly_allocations": [{"date": "2026-07-01", "weights": {"H00300.CSI": 0.25, "CASH": 0.75}}],
        "excluded_assets": [{"asset_id": "399606.SZ", "name": "创业板R", "reason": "readiness_blocked"}],
        "unavailable_assets": [],
        "benchmark": {"available": True, "rows": [{"strategy": "RESEARCH_TAA_MVP", "annual_return": 0.1}], "alpha": {"vs_hs300": 0.01}},
        "diagnostics": {"sample_period": {"reason": "common-date alignment + 252-day lookback"}, "factor_summary": {"score_observations": 5}, "selection_frequency": [{"asset_id": "H00300.CSI", "name": "沪深300收益", "selected_months": 5}]},
        "constraint_diagnostics": {"violations": [], "cash_drag": {"average_cash": 0.1}, "cap_hits": {"single_asset_cap": 1}},
        "decision": {"ready_for_execution_backtest": True, "reasons": []},
        "warnings": ["This research backtest does not replace the current V11 production candidate."],
    }


def test_research_backtest_report_missing_file(tmp_path):
    loaded = research_report.load_research_backtest_report(tmp_path / "missing.json")

    assert loaded["available"] is False
    assert loaded["message"] == "research backtest report not generated yet"


def test_research_backtest_report_write_and_load(tmp_path):
    path = tmp_path / "report.json"

    write_research_backtest_report(_sample_report(), path)
    loaded = research_report.load_research_backtest_report(path)

    assert loaded["available"] is True
    assert loaded["universe_count"] == 13




















def test_checked_in_research_backtest_report_exists():
    assert Path("reports/research_backtest_report.json").exists()
