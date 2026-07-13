import pytest
from fastapi.testclient import TestClient

from backtest.execution.proxy_report import load_proxy_research_report, write_proxy_research_report
from backtest.execution.proxy_scoring import MIN_CORRELATION, MIN_OVERLAP_DAYS, MAX_TRACKING_ERROR, score_proxy_candidate
from backend.main import app
from backtest.research.data_loader import load_research_price_dataset
from backtest.execution.data_loader import load_execution_price_dataset
from engine.asset_registry import load_execution_universe, load_research_universe


CLIENT = TestClient(app)
REPORT = load_proxy_research_report()
RESEARCH = load_research_price_dataset(load_research_universe())
EXECUTION = load_execution_price_dataset(load_execution_universe())


@pytest.mark.parametrize("item", REPORT["research_assets"])
def test_each_blocked_asset_has_manual_recommendation(item):
    assert item["recommendation"]["requires_manual_approval"] is True


@pytest.mark.parametrize("item", REPORT["research_assets"])
def test_each_blocked_asset_has_ranked_candidates(item):
    assert len(item["candidate_rankings"]) == len(EXECUTION)


@pytest.mark.parametrize("item", REPORT["research_assets"])
def test_proxy_research_preserves_current_mapping(item):
    assert {"primary_execution_proxy", "mapping_quality"} <= set(item["current_mapping"])


@pytest.mark.parametrize("item", REPORT["research_assets"])
def test_proxy_research_never_recommends_high_quality(item):
    assert item["recommendation"]["mapping_quality"] in {"none", "low", "medium"}


@pytest.mark.parametrize("item", REPORT["research_assets"])
@pytest.mark.parametrize("candidate_index", range(13))
def test_every_candidate_has_auditable_metrics(item, candidate_index):
    candidate = item["candidate_rankings"][candidate_index]
    assert {"overlap_days", "correlation", "tracking_error_annualized", "annual_return_gap", "max_drawdown_gap", "volatility_gap", "beta", "score", "hard_gate_reasons"} <= set(candidate)


def test_proxy_score_hard_gates_are_public_constants():
    assert (MIN_OVERLAP_DAYS, MIN_CORRELATION, MAX_TRACKING_ERROR) == (500, 0.65, 0.30)


def test_proxy_score_reports_insufficient_overlap():
    assert score_proxy_candidate([], [])["recommended_mapping_quality"] == "none"


def test_proxy_report_round_trip(tmp_path):
    path = write_proxy_research_report(REPORT, tmp_path / "proxy.json")
    assert load_proxy_research_report(path)["available"] is True


def test_proxy_report_missing_is_explicit(tmp_path):
    assert load_proxy_research_report(tmp_path / "missing.json")["available"] is False


def test_proxy_research_api_is_read_only():
    assert CLIENT.get("/api/research/execution-proxy-research").status_code == 200


def test_proxy_research_api_missing_report(monkeypatch, tmp_path):
    monkeypatch.setattr("backtest.execution.proxy_report.EXECUTION_PROXY_RESEARCH_REPORT", tmp_path / "missing.json")
    assert CLIENT.get("/api/research/execution-proxy-research").json()["available"] is False


def test_proxy_research_page_section_renders():
    assert "Proxy Candidate Research" in CLIENT.get("/execution-backtest").text


def test_proxy_report_states_no_automatic_mapping_mutation():
    assert "do not modify asset_mapping.json" in REPORT["warning"]
