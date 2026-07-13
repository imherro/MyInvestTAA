from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backtest.execution.mapping_application import _verify_locked_inputs
from backtest.execution.shadow_report import load_execution_aware_shadow_portfolio
from decision.current_market import build_current_market_decision, load_current_market_sources
from decision.current_market.freshness import evaluate_freshness
from decision.current_market.engine import (
    _production_candidate,
    validate_execution_decision_evidence,
)
from decision.current_market.explain import build_cash_explanation, decision_headline
from decision.current_market.report import load_current_market_decision, write_current_market_decision
from decision.current_market.source_policy import (
    ALL_SOURCE_DEFINITIONS,
    REQUIRED_SOURCE_DEFINITIONS,
    verify_current_decision_sources,
)


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
        "available",
        "metrics_available",
        "evidence_complete",
        "policy_schema_verified",
        "annual_return",
        "max_drawdown",
        "sharpe",
        "tradable_weight_coverage",
        "untradable_month_ratio",
        "gate_policy",
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
        "market_data_as_of",
        "decision_date",
        "governance_state_as_of",
        "snapshot_mode",
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
    assert candidate["allocation_available"] is True
    assert candidate["allocation"]
    assert "SHADOW" not in candidate["allocation"]
    assert candidate["unchanged"] is True
    assert candidate["allocation_source"] == "reports/v11_current_allocation.json"
    assert candidate["message"] is None


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
    assert "without an approved execution ETF" in explanation


def test_execution_gate_failure_is_preserved():
    validation = REPORT["execution_validation"]
    assert validation["ready"] is False
    assert validation["tradable_weight_coverage"] == pytest.approx(0.691469)
    assert validation["untradable_month_ratio"] == pytest.approx(1.0)
    assert validation["gate_policy"]["tradable_weight_coverage_min"] == pytest.approx(0.7)
    assert len(validation["gate_policy"]["policy_hash"]) == 64


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
    assert freshness["next_rebalance_estimate"] == "2026-07-31"
    assert freshness["estimate_basis"] == "calendar_month_end"
    assert freshness["confirmed_trading_date"] is False
    assert freshness["stale"] is False


def test_etf_freshness_uses_actual_price_dates():
    checks = REPORT["data_freshness"]["etf_prices"]["checks"]
    assert set(checks) == {"510500.SH", "512760.SH", "588000.SH"}
    assert all(row["source_as_of"] == "2026-07-08" for row in checks.values())
    assert REPORT["data_freshness"]["etf_prices"]["actual_files_verified"] is True


def test_freshness_marks_future_source_date_stale():
    result = evaluate_freshness(
        market_data_as_of="2026-07-08",
        decision_date="2026-07-13",
        governance_state_as_of="2026-07-13",
        snapshot_mode="current_decision_with_lagged_market_data",
        market_as_of="2026-07-09",
        research_date="2026-06-30",
        research_source_as_of="2026-07-08",
        execution_source_as_of="2026-07-08",
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
    assert "Decision prepared on 2026-07-13 using market data through 2026-07-08. This page does not create orders or replace V11." in text
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


@pytest.mark.parametrize(
    "field",
    [
        "decision_date",
        "generated_at",
        "market_data_as_of",
        "governance_state_as_of",
        "snapshot_mode",
        "source_hash_verification",
        "cash_explanation_components",
        "cash_reconciliation",
    ],
)
def test_fixed_report_has_temporal_and_integrity_contract(field):
    assert field in REPORT


@pytest.mark.parametrize(
    "field",
    [
        "candidate_metadata_available",
        "current_allocation_available",
        "boundary_verified",
        "unchanged",
        "allocation_source",
    ],
)
def test_fixed_v11_boundary_contract(field):
    assert field in REPORT["production_candidate"]


@pytest.mark.parametrize(
    "field",
    [
        "policy_id",
        "tradable_weight_coverage_min",
        "untradable_month_ratio_max",
        "max_drawdown_min",
        "sharpe_min",
        "annual_return_gap_min",
        "source",
        "policy_hash",
        "manifest_source",
        "available",
    ],
)
def test_execution_gate_policy_contract(field):
    assert field in REPORT["execution_validation"]["gate_policy"]


@pytest.mark.parametrize(
    "field",
    ["source", "path", "sha256", "available", "source_as_of", "required", "temporal_role"],
)
def test_fixed_source_manifest_fields(field):
    assert all(field in row for row in REPORT["source_manifest"].values())


def test_loader_preserves_generated_unavailable_state(tmp_path):
    value = copy.deepcopy(REPORT)
    value["available"] = False
    value["status"] = "unavailable"
    path = tmp_path / "unavailable.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    loaded = load_current_market_decision(path)
    assert loaded["available"] is False
    assert loaded["status"] == "unavailable"


def test_loader_rejects_malformed_json(tmp_path):
    path = tmp_path / "malformed.json"
    path.write_text("{not-json", encoding="utf-8")
    loaded = load_current_market_decision(path)
    assert loaded["available"] is False
    assert loaded["status"] == "unavailable"
    assert "invalid" in loaded["message"]


def test_loader_rejects_incomplete_schema(tmp_path):
    path = tmp_path / "incomplete.json"
    path.write_text('{"available": true}', encoding="utf-8")
    loaded = load_current_market_decision(path)
    assert loaded["available"] is False
    assert "schema is incomplete" in loaded["message"]
    assert any("decision_date" in error for error in loaded["errors"])


def test_loader_detects_required_source_hash_drift(tmp_path, monkeypatch):
    value = copy.deepcopy(REPORT)
    value["source_manifest"]["market_and_v11"]["sha256"] = "0" * 64
    path = tmp_path / "report.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    loaded = load_current_market_decision(path, verify_sources=True)
    assert loaded["available"] is False
    assert loaded["ready_for_user_review"] is False
    assert loaded["message"] == "current market decision snapshot source drifted; rebuild required"
    assert "required source hash mismatch: market_and_v11" in loaded["source_hash_verification"]["errors"]


def test_loader_detects_missing_required_source(tmp_path, monkeypatch):
    import decision.current_market.report as report_module

    value = copy.deepcopy(REPORT)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(report_module, "ROOT", tmp_path)
    loaded = load_current_market_decision(path, verify_sources=True)
    assert loaded["available"] is False
    assert "required source missing: market_and_v11" in loaded["source_hash_verification"]["errors"]


def test_loader_custom_path_skips_live_hash_verification_by_default(tmp_path):
    value = copy.deepcopy(REPORT)
    value["source_manifest"]["market_and_v11"]["sha256"] = "0" * 64
    path = tmp_path / "historical.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert load_current_market_decision(path)["available"] is True


def test_execution_report_missing_blocks_user_review():
    sources = copy.deepcopy(SOURCES)
    sources["execution"] = {"available": False}
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["execution_validation"]["available"] is False
    assert report["ready_for_user_review"] is False
    assert report["status"] == "unavailable"
    assert "execution validation report unavailable" in report["decision_summary"]["blocking_conditions"]


@pytest.mark.parametrize("field", ["annual_return", "max_drawdown", "sharpe"])
def test_execution_metric_missing_blocks_user_review(field):
    sources = copy.deepcopy(SOURCES)
    sources["execution"]["metrics"].pop(field)
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["execution_validation"]["metrics_available"] is False
    assert report["ready_for_user_review"] is False


@pytest.mark.parametrize("field", ["tradable_weight_coverage", "untradable_month_ratio"])
def test_execution_mapping_metric_missing_blocks_user_review(field):
    sources = copy.deepcopy(SOURCES)
    sources["execution"]["mapping_summary"].pop(field)
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["execution_validation"]["metrics_available"] is False
    assert report["ready_for_user_review"] is False


def test_execution_not_ready_still_permits_user_review_when_evidence_exists():
    assert REPORT["execution_validation"]["ready"] is False
    assert REPORT["execution_validation"]["available"] is True
    assert REPORT["execution_validation"]["evidence_complete"] is True
    assert REPORT["ready_for_user_review"] is True


def test_current_snapshot_has_distinct_market_and_governance_dates():
    assert REPORT["decision_date"] == "2026-07-13"
    assert REPORT["market_data_as_of"] == "2026-07-08"
    assert REPORT["governance_state_as_of"] == "2026-07-13"
    assert REPORT["snapshot_mode"] == "current_decision_with_lagged_market_data"


def test_current_mode_permits_later_governance_state():
    assert REPORT["governance_state_as_of"] > REPORT["market_data_as_of"]
    assert REPORT["data_freshness"]["temporal_status"] == "pass"
    assert REPORT["ready_for_user_review"] is True


def test_historical_mode_rejects_future_governance_state():
    report = build_current_market_decision(
        sources=copy.deepcopy(SOURCES),
        market_data_as_of="2026-07-08",
        decision_date="2026-07-13",
        snapshot_mode="historical_snapshot",
    )
    assert report["ready_for_user_review"] is False
    assert report["data_freshness"]["temporal_status"] == "invalid"
    assert "historical snapshot governance state is dated after as-of" in report["data_freshness"]["temporal_errors"]


def test_governance_after_decision_date_is_invalid():
    report = build_current_market_decision(
        sources=copy.deepcopy(SOURCES),
        market_data_as_of="2026-07-08",
        decision_date="2026-07-12",
    )
    assert report["ready_for_user_review"] is False
    assert "governance state is dated after decision date" in report["data_freshness"]["temporal_errors"]


def test_market_source_after_cutoff_fails():
    sources = copy.deepcopy(SOURCES)
    sources["diagnosis"]["dataset"]["period"]["end"] = "2026-07-09"
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["ready_for_user_review"] is False
    assert report["data_freshness"]["market_data"]["stale"] is True


def test_etf_source_after_cutoff_fails():
    sources = copy.deepcopy(SOURCES)
    for row in sources["shadow"]["price_as_of_by_proxy"].values():
        row["actual_price_date"] = "2026-07-09"
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["ready_for_user_review"] is False
    assert report["data_freshness"]["etf_prices"]["stale"] is True


def test_execution_source_after_cutoff_fails():
    sources = copy.deepcopy(SOURCES)
    sources["execution"]["period"]["end"] = "2026-07-09"
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["ready_for_user_review"] is False
    assert "execution validation report is dated after market data cutoff" in report["data_freshness"]["temporal_errors"]


def test_v11_metadata_and_current_allocation_are_available():
    candidate = REPORT["production_candidate"]
    assert candidate["candidate_metadata_available"] is True
    assert candidate["current_allocation_available"] is True
    assert candidate["boundary_verified"] is True
    assert candidate["allocation"]
    assert candidate["production_actionable"] is False


def test_missing_v11_metadata_blocks_boundary_review():
    sources = copy.deepcopy(SOURCES)
    sources["diagnosis"]["diagnosis"]["production_readiness"] = {}
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["production_candidate"]["candidate_metadata_available"] is False
    assert report["production_candidate"]["boundary_verified"] is False
    assert report["ready_for_user_review"] is False


def test_shadow_source_cannot_populate_v11():
    sources = copy.deepcopy(SOURCES)
    sources["v11_allocation"] = {
        "available": True,
        "strategy": "V11_PRODUCTION_FUSION",
        "allocation": {"SHADOW": 1.0},
        "shadow_source": True,
    }
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["production_candidate"]["boundary_verified"] is False
    assert report["ready_for_user_review"] is False


def test_v11_unchanged_is_derived_from_source_identity():
    source = Path("decision/current_market/engine.py").read_text(encoding="utf-8")
    assert '"unchanged": True' not in source
    assert REPORT["production_candidate"]["unchanged"] is True


def test_gate_policy_is_loaded_from_required_source():
    gate = REPORT["execution_validation"]["gate_policy"]
    source = REPORT["source_manifest"]["execution_gate_policy"]
    assert gate["manifest_source"] == source["path"]
    assert gate["policy_hash"] == source["sha256"]
    assert source["required"] is True


def test_gate_policy_has_no_self_asserted_unchanged_flag():
    gate = REPORT["execution_validation"]["gate_policy"]
    assert "gate_thresholds_unchanged" not in REPORT["execution_validation"]
    assert not any("unchanged" in key for key in gate)


def _cash_rows(*rows):
    return [
        {
            "research_asset_id": asset,
            "research_weight": weight,
            "destination": "CASH",
            "reason": reason,
        }
        for asset, weight, reason in rows
    ]


def test_cash_explanation_supports_multiple_research_only_assets():
    breakdown = {
        "research_cash": 0.2,
        "unmapped_cash": 0.0,
        "research_only_cash": 0.2,
        "rejected_proxy_cash": 0.0,
        "low_quality_proxy_cash": 0.0,
        "missing_price_cash": 0.0,
    }
    result = build_cash_explanation(
        breakdown,
        _cash_rows(("A", 0.1, "research_only_cash"), ("B", 0.1, "research_only_cash")),
        0.4,
    )
    component = next(row for row in result["components"] if row["category"] == "research_only_cash")
    assert [row["research_asset_id"] for row in component["assets"]] == ["A", "B"]
    assert "A, B" in result["text"]
    assert result["reconciled"] is True


@pytest.mark.parametrize(
    ("category", "asset"),
    [
        ("unmapped_cash", "UNMAPPED"),
        ("rejected_proxy_cash", "REJECTED"),
        ("low_quality_proxy_cash", "LOW"),
        ("missing_price_cash", "MISSING"),
    ],
)
def test_cash_explanation_is_data_driven_for_each_reason(category, asset):
    breakdown = {key: 0.0 for key in (
        "research_cash", "unmapped_cash", "research_only_cash", "rejected_proxy_cash", "low_quality_proxy_cash", "missing_price_cash"
    )}
    breakdown[category] = 0.1
    result = build_cash_explanation(breakdown, _cash_rows((asset, 0.1, category)), 0.1)
    component = next(row for row in result["components"] if row["category"] == category)
    assert component["assets"][0]["research_asset_id"] == asset
    assert asset in result["text"]


def test_cash_component_mismatch_blocks_review():
    sources = copy.deepcopy(SOURCES)
    sources["shadow"]["cash_breakdown"]["research_cash"] = 0.29
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["cash_reconciliation"]["reconciled"] is False
    assert report["ready_for_user_review"] is False
    assert "cash explanation components do not reconcile to Shadow cash" in report["decision_summary"]["blocking_conditions"]


def test_current_cash_components_reconcile_exactly():
    assert REPORT["cash_reconciliation"] == {
        "total_cash_weight": 0.4,
        "component_weight_sum": 0.4,
        "reconciled": True,
    }
    assert sum(row["weight"] for row in REPORT["cash_explanation_components"]) == pytest.approx(0.4)


def test_rebalance_estimate_is_explicitly_unconfirmed():
    schedule = REPORT["data_freshness"]["research_allocation"]
    assert schedule["schedule_policy"] == "last_completed_monthly_rebalance"
    assert schedule["next_rebalance_estimate"] == "2026-07-31"
    assert schedule["estimate_basis"] == "calendar_month_end"
    assert schedule["confirmed_trading_date"] is False


def test_required_source_missing_blocks_review():
    sources = copy.deepcopy(SOURCES)
    sources["source_manifest"]["execution_gate_policy"]["available"] = False
    sources["source_manifest"]["execution_gate_policy"]["sha256"] = None
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["source_hash_verification"]["valid"] is False
    assert report["ready_for_user_review"] is False


def test_optional_v11_allocation_source_may_be_missing():
    candidate = _production_candidate(
        SOURCES["diagnosis"],
        {"available": False},
        snapshot_present=False,
    )
    assert candidate["candidate_metadata_available"] is True
    assert candidate["current_allocation_available"] is False
    assert candidate["snapshot_valid_or_missing"] is True
    assert candidate["boundary_verified"] is True


def test_required_source_manifest_count_and_hashes():
    verification = REPORT["source_hash_verification"]
    assert verification["required_count"] == 9
    assert verification["available_required_count"] == 9
    assert verification["valid"] is True
    assert all(
        len(row["sha256"]) == 64
        for row in REPORT["source_manifest"].values()
        if row["required"]
    )


def test_generated_timestamp_is_explicit_utc():
    assert REPORT["generated_at"].endswith("+00:00")
    assert "T" in REPORT["generated_at"]


def test_api_exposes_temporal_and_gate_contract():
    value = CLIENT.get("/api/decision/current-market").json()
    assert value["decision_date"] == "2026-07-13"
    assert value["market_data_as_of"] == "2026-07-08"
    assert value["governance_state_as_of"] == "2026-07-13"
    assert value["execution_validation"]["gate_policy"]["policy_hash"]


@pytest.mark.parametrize(
    "section",
    [
        "Decision Date",
        "Market Data Through",
        "Governance State Date",
        "Snapshot Mode",
        "Required Source Status",
        "Execution Gate Policy",
        "V11 Metadata Available",
        "V11 Current Allocation Available",
    ],
)
def test_fixed_page_temporal_sections(section):
    assert section in CLIENT.get("/current-decision").text


def test_fixed_page_explains_lagged_market_data():
    text = CLIENT.get("/current-decision").text
    assert "Decision prepared on 2026-07-13 using market data through 2026-07-08." in text
    assert "This page does not create orders or replace V11." in text


def _build_with_execution_value(section: str, field: str, value) -> dict:
    sources = copy.deepcopy(SOURCES)
    sources["execution"].setdefault(section, {})[field] = value
    return build_current_market_decision(as_of="2026-07-08", sources=sources)


@pytest.mark.parametrize(
    ("ready", "reasons", "expected_error"),
    [
        (False, [], "ready=false requires non-empty reasons"),
        (True, ["unexpected"], "ready=true requires empty reasons"),
        (False, [1], "reason must be a string"),
        (False, [""], "reason must be non-empty"),
        (False, "not-a-list", "reasons must be list[str]"),
    ],
)
def test_execution_decision_semantic_combinations_fail_closed(
    ready, reasons, expected_error
):
    sources = copy.deepcopy(SOURCES)
    sources["execution"]["decision"]["ready_for_execution_validation"] = ready
    sources["execution"]["decision"]["reasons"] = reasons
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["execution_validation"]["available"] is False
    assert report["execution_validation"]["evidence_complete"] is False
    assert report["ready_for_user_review"] is False
    assert any(
        expected_error in error
        for error in report["execution_validation"]["semantic_errors"]
    )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        (section, field, value)
        for section, fields in (
            ("metrics", ("annual_return", "max_drawdown", "sharpe")),
            (
                "mapping_summary",
                ("tradable_weight_coverage", "untradable_month_ratio"),
            ),
        )
        for field in fields
        for value in (float("nan"), float("inf"), float("-inf"))
    ],
)
def test_execution_nonfinite_metrics_fail_closed(section, field, value):
    report = _build_with_execution_value(section, field, value)
    assert report["execution_validation"]["metrics_available"] is False
    assert report["execution_validation"]["available"] is False
    assert report["ready_for_user_review"] is False
    assert any(field in error for error in report["execution_validation"]["semantic_errors"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tradable_weight_coverage", -0.01),
        ("tradable_weight_coverage", 1.01),
        ("untradable_month_ratio", -0.01),
        ("untradable_month_ratio", 1.01),
    ],
)
def test_execution_ratio_metrics_must_be_bounded(field, value):
    report = _build_with_execution_value("mapping_summary", field, value)
    assert report["execution_validation"]["available"] is False
    assert any("between 0 and 1" in error for error in report["execution_validation"]["semantic_errors"])


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("start", None, "execution period start is required"),
        ("end", None, "execution period end is required"),
        ("start", "2026-07-09", "execution period start must not be after end"),
    ],
)
def test_execution_period_semantics_fail_closed(field, value, expected_error):
    report = _build_with_execution_value("period", field, value)
    assert report["execution_validation"]["available"] is False
    assert expected_error in report["execution_validation"]["semantic_errors"]


@pytest.mark.parametrize(
    "field",
    [
        "policy_id",
        "tradable_weight_coverage_min",
        "untradable_month_ratio_max",
        "max_drawdown_min",
        "sharpe_min",
        "annual_return_gap_min",
        "source",
    ],
)
def test_gate_policy_missing_field_fails_closed(field):
    sources = copy.deepcopy(SOURCES)
    sources["gate_policy"].pop(field)
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    gate = report["execution_validation"]["gate_policy"]
    assert gate["policy_schema_verified"] is False
    assert report["ready_for_user_review"] is False


@pytest.mark.parametrize(
    "field",
    [
        "tradable_weight_coverage_min",
        "untradable_month_ratio_max",
        "max_drawdown_min",
        "sharpe_min",
        "annual_return_gap_min",
    ],
)
def test_gate_policy_nonfinite_threshold_fails_closed(field):
    sources = copy.deepcopy(SOURCES)
    sources["gate_policy"][field] = float("nan")
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["execution_validation"]["gate_policy"]["policy_schema_verified"] is False
    assert any(field in error for error in report["execution_validation"]["semantic_errors"])


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("required", False, "source required flag mismatch"),
        ("path", "reports/other.json", "source path mismatch"),
        ("temporal_role", "governance", "source temporal role mismatch"),
        ("source", "other", "source identity mismatch"),
    ],
)
def test_canonical_required_source_metadata_fails_closed(field, value, expected_error):
    sources = copy.deepcopy(SOURCES)
    sources["source_manifest"]["market_and_v11"][field] = value
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["source_hash_verification"]["valid"] is False
    assert report["ready_for_user_review"] is False
    assert any(expected_error in error for error in report["source_hash_verification"]["errors"])


def test_unknown_required_source_fails_closed():
    sources = copy.deepcopy(SOURCES)
    sources["source_manifest"]["unknown_required"] = {
        "source": "unknown_required",
        "path": "reports/unknown.json",
        "sha256": "0" * 64,
        "available": True,
        "source_as_of": None,
        "required": True,
        "temporal_role": "market_data",
    }
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert "unknown required source: unknown_required" in report["source_hash_verification"]["errors"]
    assert report["ready_for_user_review"] is False


def test_policy_manifest_hash_mismatch_fails_semantic_validation():
    source = copy.deepcopy(SOURCES["source_manifest"]["execution_gate_policy"])
    source["sha256"] = "0" * 64
    result = validate_execution_decision_evidence(
        copy.deepcopy(SOURCES["execution"]),
        copy.deepcopy(SOURCES["gate_policy"]),
        source,
    )
    assert result["valid"] is False
    assert result["policy_hash_verified"] is False
    assert "required source hash mismatch: execution_gate_policy" in result["errors"]


def test_build_and_loader_use_the_same_source_verifier():
    expected = verify_current_decision_sources(REPORT["source_manifest"])
    assert REPORT["source_hash_verification"] == expected
    assert expected == {
        "valid": True,
        "required_count": 9,
        "available_required_count": 9,
        "verified_count": 9,
        "errors": [],
    }
    assert len(REQUIRED_SOURCE_DEFINITIONS) == 9
    assert len(ALL_SOURCE_DEFINITIONS) == 10


@pytest.mark.parametrize(
    ("status", "ready", "expected"),
    [
        ("user_review_ready", True, "Verified local allocation snapshot ready for user review"),
        ("stale", False, "Historical verified decision snapshot"),
        ("unavailable", False, "Decision snapshot unavailable for user review"),
    ],
)
def test_decision_headline_tracks_final_status(status, ready, expected):
    assert decision_headline(status=status, ready_for_user_review=ready) == expected


def test_current_report_business_result_is_unchanged_after_semantic_hardening():
    assert REPORT["market_state"]["regime"] == "bull_caution"
    assert REPORT["ready_for_user_review"] is True
    assert REPORT["production_actionable"] is False
    assert REPORT["production_candidate"]["current_allocation_available"] is True
    assert REPORT["execution_shadow"]["etf_weights"] == {
        "510500.SH": 0.25,
        "512760.SH": 0.1,
        "588000.SH": 0.25,
        "CASH": 0.4,
    }
    assert REPORT["execution_validation"]["ready"] is False
    assert REPORT["execution_validation"]["tradable_weight_coverage"] == pytest.approx(0.691469)
    assert REPORT["execution_validation"]["untradable_month_ratio"] == 1.0


def test_unavailable_web_page_never_claims_ready(monkeypatch):
    monkeypatch.setattr(
        "backend.main.load_current_market_decision",
        lambda: {
            "available": False,
            "status": "unavailable",
            "ready_for_user_review": False,
            "production_actionable": False,
            "decision_summary": {
                "headline": "Verified local allocation snapshot ready for user review"
            },
        },
    )
    text = CLIENT.get("/current-decision").text
    assert "Decision snapshot unavailable for user review" in text
    assert "Verified local allocation snapshot ready for user review" not in text
