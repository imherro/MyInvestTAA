from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backtest.execution.mapping_application import _verify_locked_inputs
from backtest.execution.shadow_report import load_execution_aware_shadow_portfolio
from decision.current_market import build_current_market_decision, load_current_market_sources
from decision.current_market.freshness import evaluate_freshness
from decision.current_market.report import load_current_market_decision, write_current_market_decision


CLIENT = TestClient(app)
SOURCES = load_current_market_sources()
REPORT = build_current_market_decision(as_of="2026-07-08", sources=SOURCES)


@pytest.mark.parametrize(
    "field",
    [
        "available",
        "status",
        "ready_for_user_review",
        "production_actionable",
        "as_of",
        "market_state",
        "production_candidate",
        "research_allocation",
        "execution_shadow",
        "execution_validation",
        "comparison",
        "risk_summary",
        "cash_explanation",
        "decision_summary",
        "data_freshness",
        "source_manifest",
        "warnings",
    ],
)
def test_report_top_level_contract(field):
    assert field in REPORT


@pytest.mark.parametrize(
    "field",
    [
        "available",
        "regime",
        "risk_level",
        "trend_state",
        "trend_score",
        "confidence",
        "evidence",
        "source",
        "source_as_of",
    ],
)
def test_market_state_contract(field):
    assert field in REPORT["market_state"]


@pytest.mark.parametrize(
    "field",
    [
        "strategy",
        "available",
        "allocation_available",
        "unchanged",
        "allocation",
        "risk_controls",
        "production_readiness",
        "source",
        "source_as_of",
        "message",
    ],
)
def test_v11_candidate_contract(field):
    assert field in REPORT["production_candidate"]


@pytest.mark.parametrize(
    "field",
    ["available", "strategy", "allocation_date", "weights", "status", "source", "source_as_of"],
)
def test_research_allocation_contract(field):
    assert field in REPORT["research_allocation"]


@pytest.mark.parametrize(
    "field",
    [
        "available",
        "status",
        "production_approved",
        "data_as_of",
        "etf_weights",
        "cash_breakdown",
        "mapping_explanations",
        "constraint_checks",
        "snapshot_integrity",
        "approval_integrity",
        "price_as_of_by_proxy",
        "source",
        "source_as_of",
    ],
)
def test_shadow_contract(field):
    assert field in REPORT["execution_shadow"]


@pytest.mark.parametrize(
    "field",
    [
        "ready",
        "reasons",
        "annual_return",
        "max_drawdown",
        "sharpe",
        "tradable_weight_coverage",
        "untradable_month_ratio",
        "gate_thresholds_unchanged",
        "source",
        "source_as_of",
    ],
)
def test_execution_validation_contract(field):
    assert field in REPORT["execution_validation"]


@pytest.mark.parametrize(
    "field",
    [
        "status",
        "as_of",
        "market_data",
        "etf_prices",
        "research_allocation",
        "approval_integrity_verified",
        "shadow_snapshot_verified",
        "errors",
    ],
)
def test_freshness_contract(field):
    assert field in REPORT["data_freshness"]


@pytest.mark.parametrize(
    "source",
    [
        "market_and_v11",
        "research_allocation",
        "execution_validation",
        "execution_shadow",
        "execution_price_manifest",
        "approval_integrity",
        "decision_ledger",
        "asset_mapping",
    ],
)
@pytest.mark.parametrize("field", ["source", "path", "sha256", "available", "source_as_of"])
def test_source_manifest_contract(source, field):
    assert field in REPORT["source_manifest"][source]


def test_current_snapshot_is_ready_for_user_review_only():
    assert REPORT["available"] is True
    assert REPORT["status"] == "user_review_ready"
    assert REPORT["ready_for_user_review"] is True
    assert REPORT["production_actionable"] is False


def test_market_state_reuses_formal_regime_source():
    assert REPORT["market_state"]["regime"] == "bull_caution"
    assert REPORT["market_state"]["risk_level"] == "high_mixed_trend"
    assert "regime_v3" in REPORT["market_state"]["source"]


def test_v11_is_never_filled_from_shadow():
    candidate = REPORT["production_candidate"]
    assert candidate["strategy"] == "V11_PRODUCTION_FUSION"
    assert candidate["allocation_available"] is False
    assert candidate["allocation"] == {}
    assert candidate["unchanged"] is True
    assert candidate["message"] == "current V11 allocation source unavailable"


def test_v11_and_shadow_are_side_by_side_only():
    assert REPORT["comparison"]["mode"] == "side_by_side_only"
    assert REPORT["comparison"]["merged_portfolio_created"] is False
    assert REPORT["comparison"]["v11_vs_research_shadow"]["automatic_selection"] is False


def test_research_and_shadow_weights_are_exact():
    assert REPORT["research_allocation"]["allocation_date"] == "2026-06-30"
    assert REPORT["execution_shadow"]["etf_weights"] == {
        "510500.SH": 0.25,
        "512760.SH": 0.1,
        "588000.SH": 0.25,
        "CASH": 0.4,
    }


def test_cash_explanation_names_both_components_and_computing_power():
    explanation = REPORT["cash_explanation"]
    assert "40%" in explanation
    assert "30%" in explanation
    assert "10%" in explanation
    assert "931688CNY010.CSI" in explanation
    assert "算力" in explanation
    assert "no approved execution ETF" in explanation


def test_execution_gate_failure_is_preserved():
    validation = REPORT["execution_validation"]
    assert validation["ready"] is False
    assert validation["tradable_weight_coverage"] == pytest.approx(0.691469)
    assert validation["untradable_month_ratio"] == pytest.approx(1.0)
    assert validation["gate_thresholds_unchanged"] is True


def test_risk_summary_respects_shadow_constraints():
    risk = REPORT["risk_summary"]
    assert risk["equity_weight"] == pytest.approx(0.6)
    assert risk["cash_weight"] == pytest.approx(0.4)
    assert risk["single_etf_limit"] == pytest.approx(0.35)
    assert risk["constraint_violations"] == []


def test_stale_market_snapshot_is_historical_only():
    sources = copy.deepcopy(SOURCES)
    sources["diagnosis"]["dataset"]["period"]["end"] = "2026-06-01"
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["status"] == "stale"
    assert report["ready_for_user_review"] is False
    assert report["production_actionable"] is False
    assert report["decision_summary"]["headline"] == "Historical verified decision snapshot"


def test_missing_market_state_makes_report_unavailable():
    sources = copy.deepcopy(SOURCES)
    sources["diagnosis"] = {"available": False}
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["available"] is False
    assert report["status"] in {"stale", "unavailable"}
    assert report["production_actionable"] is False


def test_price_verification_failure_blocks_review():
    sources = copy.deepcopy(SOURCES)
    sources["price_verification"] = {
        "provenance_verified": False,
        "errors": ["price file sha256 mismatch: 510500.SH"],
    }
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["ready_for_user_review"] is False
    assert "510500.SH" in " ".join(report["data_freshness"]["errors"])


def test_approval_gate_failure_blocks_review():
    sources = copy.deepcopy(SOURCES)
    sources["approval_integrity"]["validation"]["ledger_verified"] = False
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["ready_for_user_review"] is False
    assert report["data_freshness"]["approval_integrity_verified"] is False


def test_shadow_constraint_violation_blocks_review():
    sources = copy.deepcopy(SOURCES)
    sources["shadow"]["constraint_checks"]["violations"] = [
        {"asset_id": "510500.SH", "weight": 0.4, "limit": 0.35}
    ]
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["ready_for_user_review"] is False
    assert report["risk_summary"]["constraint_violations"]


def test_shadow_weight_sum_failure_blocks_review():
    sources = copy.deepcopy(SOURCES)
    sources["shadow"]["execution_weights"]["CASH"] = 0.39
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["ready_for_user_review"] is False


def test_monthly_research_allocation_is_not_daily_stale():
    freshness = REPORT["data_freshness"]["research_allocation"]
    assert freshness["expected_cadence"] == "monthly"
    assert freshness["next_scheduled_rebalance"] == "2026-07-31"
    assert freshness["stale"] is False


def test_etf_freshness_uses_actual_price_dates():
    checks = REPORT["data_freshness"]["etf_prices"]["checks"]
    assert set(checks) == {"510500.SH", "512760.SH", "588000.SH"}
    assert all(row["source_as_of"] == "2026-07-08" for row in checks.values())
    assert REPORT["data_freshness"]["etf_prices"]["actual_files_verified"] is True


def test_freshness_marks_future_source_date_stale():
    result = evaluate_freshness(
        as_of="2026-07-08",
        market_as_of="2026-07-09",
        research_date="2026-06-30",
        shadow=SOURCES["shadow"],
        approval_integrity=SOURCES["approval_integrity"],
        price_verification=SOURCES["price_verification"],
    )
    assert result["status"] == "stale"
    assert "after requested as-of" in result["market_data"]["message"]


def test_shadow_loader_reverifies_actual_price_files(monkeypatch):
    monkeypatch.setattr(
        "backtest.execution.dataset_provenance.verify_price_dataset_manifest",
        lambda *args, **kwargs: {
            "provenance_verified": False,
            "errors": ["price file row_count mismatch: 510500.SH"],
        },
    )
    report = load_execution_aware_shadow_portfolio()
    assert report["available"] is False
    assert report["message"] == "shadow snapshot integrity verification failed"
    assert "510500.SH" in " ".join(report["errors"])


def _locked_files(tmp_path: Path):
    paths = [tmp_path / name for name in ("mapping.json", "package.json", "ledger.json")]
    for index, path in enumerate(paths):
        path.write_text(f"{{\"value\": {index}}}\n", encoding="utf-8")
    record = tmp_path / "record.json"
    return paths, record


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_transaction_lock_rejects_ledger_drift(tmp_path):
    (mapping, package, ledger), record = _locked_files(tmp_path)
    expected = (_digest(mapping), _digest(package), _digest(ledger))
    ledger.write_text('{"changed": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="decision ledger changed"):
        _verify_locked_inputs(mapping, package, ledger, record, *expected, False, None)


def test_transaction_lock_rejects_record_creation(tmp_path):
    (mapping, package, ledger), record = _locked_files(tmp_path)
    expected = (_digest(mapping), _digest(package), _digest(ledger))
    record.write_text('{"created": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="record existence changed"):
        _verify_locked_inputs(mapping, package, ledger, record, *expected, False, None)


def test_transaction_lock_rejects_record_hash_drift(tmp_path):
    (mapping, package, ledger), record = _locked_files(tmp_path)
    record.write_text('{"value": 1}\n', encoding="utf-8")
    record_hash = _digest(record)
    record.write_text('{"value": 2}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="approval record changed"):
        _verify_locked_inputs(
            mapping,
            package,
            ledger,
            record,
            _digest(mapping),
            _digest(package),
            _digest(ledger),
            True,
            record_hash,
        )


def test_report_round_trip(tmp_path):
    path = tmp_path / "current_market_decision.json"
    write_current_market_decision(REPORT, path)
    loaded = load_current_market_decision(path)
    assert loaded["status"] == "user_review_ready"
    assert loaded["production_actionable"] is False


def test_report_loader_missing(tmp_path):
    report = load_current_market_decision(tmp_path / "missing.json")
    assert report == {
        "available": False,
        "message": "current market decision report not generated yet",
    }


def test_current_decision_api_reads_local_report():
    response = CLIENT.get("/api/decision/current-market")
    assert response.status_code == 200
    assert response.json()["status"] == "user_review_ready"
    assert response.json()["production_actionable"] is False


def test_current_decision_api_missing_report_does_not_500(monkeypatch):
    monkeypatch.setattr(
        "backend.main.load_current_market_decision",
        lambda: {"available": False, "message": "missing"},
    )
    response = CLIENT.get("/api/decision/current-market")
    assert response.status_code == 200
    assert response.json() == {"available": False, "message": "missing"}


def test_current_decision_api_never_calls_tushare(monkeypatch):
    monkeypatch.setattr(
        "data_provider.tushare_provider.TushareProvider._client",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no live fetch")),
    )
    assert CLIENT.get("/api/decision/current-market").status_code == 200


@pytest.mark.parametrize(
    "section",
    [
        "Current Market State",
        "Risk Level",
        "V11 Production Candidate",
        "Research Allocation",
        "Execution-Aware Shadow Allocation",
        "Why 40% Cash?",
        "Execution Validation Status",
        "Current Constraints",
        "Data Freshness",
        "Source Provenance",
        "What Is Executable",
        "What Is Research-Only",
        "Blocking Conditions",
        "V11 vs Shadow Boundary",
    ],
)
def test_current_decision_page_sections(section):
    response = CLIENT.get("/current-decision")
    assert response.status_code == 200
    assert section in response.text


def test_current_decision_page_has_exact_warning_and_unified_shell():
    text = CLIENT.get("/current-decision").text
    assert "This page summarizes the latest verified local decision snapshot. It does not create orders or replace V11." in text
    assert "https://invest.okbbc.com/header.js" in text
    assert "https://invest.okbbc.com/footer.js" in text


def test_current_decision_page_has_no_order_form():
    text = CLIENT.get("/current-decision").text.lower()
    assert "<form" not in text
    assert "method=\"post\"" not in text
    assert "merged portfolio" in text


@pytest.mark.parametrize("page", ["/", "/research-backtest", "/execution-backtest", "/shadow-portfolio"])
def test_existing_pages_link_to_current_decision(page):
    assert 'href="/current-decision"' in CLIENT.get(page).text
