import pytest
from types import SimpleNamespace
from datetime import date, timedelta
from fastapi.testclient import TestClient

from backtest.execution.proxy_report import load_proxy_research_report, write_proxy_research_report
from backtest.execution.proxy_scoring import MIN_CORRELATION, MIN_OVERLAP_DAYS, MAX_TRACKING_ERROR, score_proxy_candidate
from backtest.execution import proxy_scoring
from backtest.execution.proxy_research import build_proxy_research_report
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


def test_annual_return_does_not_add_an_extra_principal():
    assert proxy_scoring._annual_return([0.0] * 252) == pytest.approx(0.0)


@pytest.mark.parametrize("values, expected", [
    ([], 0.0), ([0.0] * 252, 0.0), ([0.01] * 252, (1.01 ** 252) - 1.0),
    ([-0.01] * 252, (0.99 ** 252) - 1.0), ([-1.0], -1.0),
])
def test_annual_return_matches_compound_definition(values, expected):
    assert proxy_scoring._annual_return(values) == pytest.approx(expected)


@pytest.mark.parametrize("return_value", [-0.02, -0.01, 0.0, 0.01, 0.02])
def test_identical_curves_have_zero_annual_return_gap(return_value):
    rows = _rows([return_value] * 600)
    assert score_proxy_candidate(rows, rows)["annual_return_gap"] == pytest.approx(0.0)


@pytest.mark.parametrize("days", [0, 1, 100, 499, 500])
def test_overlap_gate_boundary(days):
    returns = ([0.001, -0.001] * ((days + 1) // 2))[:days]
    result = score_proxy_candidate(_rows(returns), _rows(returns))
    assert result["eligible_for_recommendation"] is (days >= 500)


@pytest.mark.parametrize("returns", [[0.001, -0.001] * 300, [0.001] * 600, [-0.001] * 600, [0.0] * 600, [0.002, -0.001, 0.001] * 200])
def test_candidate_eligibility_field_is_boolean(returns):
    result = score_proxy_candidate(_rows(returns), _rows(returns))
    assert isinstance(result["eligible_for_recommendation"], bool)


@pytest.mark.parametrize("candidate_returns", [[0.001, -0.001] * 300, [0.002, -0.002] * 300, [0.001] * 600, [-0.001] * 600, [0.003, -0.002, 0.001] * 200])
def test_score_has_all_hard_gate_fields(candidate_returns):
    result = score_proxy_candidate(_rows([0.001, -0.001] * 300), _rows(candidate_returns))
    assert {"eligible_for_recommendation", "hard_gate_reasons"} <= set(result)


def test_recommendation_uses_next_eligible_candidate(monkeypatch):
    calls = iter([
        {"score": 0.99, "eligible_for_recommendation": False, "recommended_mapping_quality": "low", "hard_gate_reasons": ["correlation_below_0.65"]},
        {"score": 0.80, "eligible_for_recommendation": True, "recommended_mapping_quality": "medium", "hard_gate_reasons": []},
    ])
    monkeypatch.setattr("backtest.execution.proxy_research.score_proxy_candidate", lambda *args: next(calls))
    report = build_proxy_research_report({"A": []}, {"X": [], "Y": []}, [SimpleNamespace(research_asset_id="A", primary_execution_proxy=None, mapping_quality="none")], ["A"])
    assert report["research_assets"][0]["recommendation"]["primary_execution_proxy"] == "Y"


def test_recommendation_keeps_research_only_without_eligible_candidate(monkeypatch):
    monkeypatch.setattr("backtest.execution.proxy_research.score_proxy_candidate", lambda *args: {"score": 0.99, "eligible_for_recommendation": False, "recommended_mapping_quality": "low", "hard_gate_reasons": ["correlation_below_0.65"]})
    report = build_proxy_research_report({"A": []}, {"X": []}, [SimpleNamespace(research_asset_id="A", primary_execution_proxy=None, mapping_quality="none")], ["A"])
    assert report["research_assets"][0]["recommendation"]["action"] == "keep_research_only"


def _rows(returns):
    price = 100.0
    result = [SimpleNamespace(date="2020-01-01", close=price)]
    for index, value in enumerate(returns, start=1):
        price *= 1.0 + value
        result.append(SimpleNamespace(date=(date(2020, 1, 1) + timedelta(days=index)).isoformat(), close=price))
    return result


def test_proxy_report_round_trip(tmp_path):
    path = write_proxy_research_report(REPORT, tmp_path / "proxy.json")
    assert load_proxy_research_report(path)["available"] is True


def test_proxy_report_missing_is_explicit(tmp_path):
    assert load_proxy_research_report(tmp_path / "missing.json")["available"] is False








def test_proxy_report_states_no_automatic_mapping_mutation():
    assert "do not modify asset_mapping.json" in REPORT["warning"]
