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


def test_research_backtest_api_missing_report(monkeypatch, tmp_path):
    monkeypatch.setattr(research_report, "RESEARCH_BACKTEST_REPORT", tmp_path / "missing.json")

    response = client.get("/api/research/research-backtest")

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_research_backtest_api_existing_report(monkeypatch, tmp_path):
    path = tmp_path / "report.json"
    write_research_backtest_report(_sample_report(), path)
    monkeypatch.setattr(research_report, "RESEARCH_BACKTEST_REPORT", path)

    response = client.get("/api/research/research-backtest")

    assert response.status_code == 200
    assert response.json()["universe_count"] == 13


def test_research_backtest_page_missing_report(monkeypatch, tmp_path):
    monkeypatch.setattr(research_report, "RESEARCH_BACKTEST_REPORT", tmp_path / "missing.json")

    response = client.get("/research-backtest")

    assert response.status_code == 200
    assert "research backtest report not generated yet" in response.text


def test_research_backtest_page_existing_report(monkeypatch, tmp_path):
    path = tmp_path / "report.json"
    write_research_backtest_report(_sample_report(), path)
    monkeypatch.setattr(research_report, "RESEARCH_BACKTEST_REPORT", path)

    response = client.get("/research-backtest")

    assert response.status_code == 200
    assert "Research Backtest" in response.text
    assert "RESEARCH_TAA_MVP" in response.text
    assert "does not replace" in response.text


def test_homepage_links_to_research_backtest():
    response = client.get("/")

    assert response.status_code == 200
    assert "/research-backtest" in response.text


def test_research_universe_links_to_research_backtest():
    response = client.get("/research-universe")

    assert response.status_code == 200
    assert "/research-backtest" in response.text


def test_research_backtest_api_does_not_require_tushare(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Tushare must not be called by API")

    monkeypatch.setattr("data_provider.tushare_provider.TushareProvider._client", fail_if_called)

    response = client.get("/api/research/research-backtest")

    assert response.status_code == 200


def test_checked_in_research_backtest_report_exists():
    assert Path("reports/research_backtest_report.json").exists()
