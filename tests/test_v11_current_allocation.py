from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from decision.current_market import (
    build_current_market_decision,
    load_current_market_decision,
    load_current_market_sources,
)
from decision.current_market.freshness import evaluate_freshness
from decision.v11_current import (
    build_v11_current_allocation_snapshot,
    load_v11_current_allocation,
    write_v11_current_allocation,
)
from decision.v11_current.report import verify_v11_current_allocation_sources
from decision.v11_current.validation import (
    canonical_state_hash,
    validate_v11_state_source,
)
from data_pipeline.strategy_diagnosis import _v11_current_state_source


CLIENT = TestClient(app)
DIAGNOSIS_PATH = Path("reports/strategy_diagnosis_report.json")
SNAPSHOT_PATH = Path("reports/v11_current_allocation.json")
DIAGNOSIS = json.loads(DIAGNOSIS_PATH.read_text(encoding="utf-8"))
SOURCE = DIAGNOSIS["diagnosis"]["v11_current_state_source"]
SNAPSHOT = load_v11_current_allocation()


def _minimal_diagnosis(source: dict | None = None, *, end: str = "2026-07-08") -> dict:
    return {
        "dataset": {"period": {"start": "2016-01-01", "end": end}},
        "diagnosis": {
            "v11_current_state_source": copy.deepcopy(source or SOURCE)
        },
    }


def _build_from_source(
    tmp_path: Path,
    mutate=None,
    *,
    recompute_hash: bool = True,
    market_data_as_of: str = "2026-07-08",
    dataset_end: str = "2026-07-08",
) -> dict:
    source = copy.deepcopy(SOURCE)
    if mutate:
        mutate(source)
    if recompute_hash:
        source["source_state_hash"] = canonical_state_hash(source)
    diagnosis = _minimal_diagnosis(source, end=dataset_end)
    path = tmp_path / "diagnosis.json"
    path.write_text(json.dumps(diagnosis, ensure_ascii=False), encoding="utf-8")
    return build_v11_current_allocation_snapshot(
        diagnosis,
        market_data_as_of=market_data_as_of,
        generated_at="2026-07-13T00:00:00+00:00",
        diagnosis_report_path=path,
    )


@pytest.mark.parametrize(
    "field",
    [
        "available",
        "strategy",
        "state_date",
        "period",
        "weights_percent",
        "selected_assets",
        "regime",
        "risk_budget",
        "exposure_decision",
        "target_weights_percent",
        "assumptions",
        "source_state_hash",
        "warnings",
    ],
)
def test_strategy_diagnosis_exposes_canonical_v11_state_field(field):
    assert field in SOURCE


@pytest.mark.parametrize(
    "field",
    [
        "available",
        "strategy",
        "status",
        "production_candidate",
        "production_actionable",
        "trading_instruction",
        "as_of",
        "source_state_date",
        "generated_at",
        "report_path",
        "allocation",
        "allocation_percent",
        "equity_weight",
        "cash_weight",
        "selected_assets",
        "regime",
        "risk_budget",
        "exposure_decision",
        "target_weights_percent",
        "assumptions",
        "source_integrity",
        "constraint_checks",
        "errors",
        "warnings",
    ],
)
def test_v11_snapshot_top_level_contract(field):
    assert field in SNAPSHOT


@pytest.mark.parametrize(
    "field",
    [
        "diagnosis_report_path",
        "diagnosis_report_hash",
        "source_state_hash",
        "taa_engine_path",
        "taa_engine_hash",
        "strategy_diagnosis_code_path",
        "strategy_diagnosis_code_hash",
        "verified",
        "errors",
    ],
)
def test_v11_snapshot_source_integrity_contract(field):
    assert field in SNAPSHOT["source_integrity"]


@pytest.mark.parametrize(
    "field",
    [
        "weight_sum_percent",
        "weight_sum_fraction",
        "negative_weights",
        "selected_asset_mismatches",
        "violations",
    ],
)
def test_v11_snapshot_constraint_contract(field):
    assert field in SNAPSHOT["constraint_checks"]


def test_v11_snapshot_uses_actual_state_weights_not_target_weights(tmp_path):
    def mutate(source):
        source["weights_percent"] = {"ACTUAL": 60.0, "CASH": 40.0}
        source["selected_assets"] = ["ACTUAL"]
        source["target_weights_percent"] = {"TARGET": 80.0, "CASH": 20.0}

    snapshot = _build_from_source(tmp_path, mutate)
    assert snapshot["available"] is True
    assert snapshot["allocation_percent"] == {"ACTUAL": 60.0, "CASH": 40.0}
    assert snapshot["allocation"] == {"ACTUAL": 0.6, "CASH": 0.4}
    assert snapshot["target_weights_percent"] == {"TARGET": 80.0, "CASH": 20.0}


def test_diagnosis_extracts_latest_actual_state_weights():
    result = {
        "period": {"start": "2026-05-31", "end": "2026-07-08"},
        "assumptions": copy.deepcopy(SOURCE["assumptions"]),
        "states": [
            {
                "date": "2026-06-30",
                "weights": {"OLD": 50.0, "CASH": 50.0},
                "signals": {"target_weights": {"OLD_TARGET": 80.0, "CASH": 20.0}},
                "regime": {"state": "neutral"},
            },
            {
                "date": "2026-07-08",
                "weights": {"ACTUAL": 60.0, "CASH": 40.0},
                "signals": {
                    "target_weights": {"TARGET": 80.0, "CASH": 20.0},
                    "risk_budget": {"equity_limit": 80.0},
                    "exposure_decision": {"equity_target": 80.0},
                },
                "regime": {"state": "bull"},
            },
        ],
    }
    source = _v11_current_state_source(result)
    assert source["state_date"] == "2026-07-08"
    assert source["weights_percent"] == {"ACTUAL": 60.0, "CASH": 40.0}
    assert source["target_weights_percent"] == {"TARGET": 80.0, "CASH": 20.0}
    assert source["selected_assets"] == ["ACTUAL"]
    assert "states" not in source


def test_formal_v11_snapshot_weight_units_reconcile():
    assert sum(SNAPSHOT["allocation_percent"].values()) == pytest.approx(100.0, abs=1e-6)
    assert sum(SNAPSHOT["allocation"].values()) == pytest.approx(1.0, abs=1e-8)
    assert SNAPSHOT["constraint_checks"]["weight_sum_percent"] == 100.0
    assert SNAPSHOT["constraint_checks"]["weight_sum_fraction"] == 1.0


def test_formal_v11_snapshot_cash_and_equity_reconcile():
    assert "CASH" in SNAPSHOT["allocation"]
    assert SNAPSHOT["equity_weight"] == pytest.approx(1 - SNAPSHOT["cash_weight"])
    assert SNAPSHOT["equity_weight"] + SNAPSHOT["cash_weight"] == pytest.approx(1.0)


def test_formal_selected_assets_match_positive_non_cash_weights():
    expected = sorted(
        asset_id
        for asset_id, weight in SNAPSHOT["allocation"].items()
        if asset_id != "CASH" and weight > 0
    )
    assert sorted(SNAPSHOT["selected_assets"]) == expected


@pytest.mark.parametrize(
    ("asset", "value", "expected"),
    [
        ("A", -1.0, "negative weights"),
        ("A", float("nan"), "must be finite"),
        ("A", float("inf"), "must be finite"),
        ("A", float("-inf"), "must be finite"),
        ("CASH", -0.1, "negative weights"),
        ("CASH", float("nan"), "must be finite"),
        ("CASH", float("inf"), "must be finite"),
        ("CASH", float("-inf"), "must be finite"),
    ],
)
def test_nonfinite_or_negative_v11_weights_fail_closed(asset, value, expected):
    source = copy.deepcopy(SOURCE)
    source["weights_percent"] = {"A": 80.0, "CASH": 20.0}
    source["weights_percent"][asset] = value
    source["selected_assets"] = ["A"]
    result = validate_v11_state_source(source, "2026-07-08")
    assert result.valid is False
    assert any(expected in error for error in result.errors)


@pytest.mark.parametrize(
    ("weights", "expected"),
    [
        ({"A": 80.0}, "must include CASH"),
        ({"A": 70.0, "CASH": 20.0}, "must sum to 100"),
        ({}, "non-empty object"),
    ],
)
def test_invalid_weight_structures_fail_closed(tmp_path, weights, expected):
    def mutate(source):
        source["weights_percent"] = weights
        source["selected_assets"] = [
            key for key, value in weights.items() if key != "CASH" and value > 0
        ]

    snapshot = _build_from_source(tmp_path, mutate)
    assert snapshot["available"] is False
    assert any(expected in error for error in snapshot["errors"])
    assert snapshot["allocation"] == {}


@pytest.mark.parametrize(
    "selected",
    [[], ["MISSING"], ["510300", "MISSING"]],
)
def test_selected_asset_mismatch_fails_closed(tmp_path, selected):
    snapshot = _build_from_source(
        tmp_path, lambda source: source.update(selected_assets=selected)
    )
    assert snapshot["available"] is False
    assert "V11 selected_assets do not match positive non-cash weights" in snapshot["errors"]


def test_duplicate_selected_assets_fail_closed(tmp_path):
    selected = list(SOURCE["selected_assets"])
    snapshot = _build_from_source(
        tmp_path,
        lambda source: source.update(selected_assets=selected + [selected[0]]),
    )
    assert snapshot["available"] is False
    assert "V11 selected_assets must not contain duplicates" in snapshot["errors"]


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("score_version", "v10", "score_version"),
        ("max_weight_step", 9.0, "max_weight_step"),
        ("volatility_adjustment", False, "volatility_adjustment"),
        ("robust_exposure_config", {}, "robust_exposure_config"),
    ],
)
def test_noncanonical_v11_assumptions_fail_closed(tmp_path, field, value, expected):
    def mutate(source):
        source["assumptions"][field] = value

    snapshot = _build_from_source(tmp_path, mutate)
    assert snapshot["available"] is False
    assert any(expected in error for error in snapshot["errors"])


@pytest.mark.parametrize(
    ("mutation", "market_as_of", "expected"),
    [
        (lambda source: source.update(strategy="OTHER"), "2026-07-08", "strategy identity"),
        (lambda source: source.update(state_date="bad-date"), "2026-07-08", "valid ISO date"),
        (lambda source: source.update(state_date="2026-07-09"), "2026-07-08", "after market data cutoff"),
        (lambda source: source["period"].update(end="2026-07-07"), "2026-07-08", "must equal result period end"),
        (lambda source: source["period"].update(start="bad-date"), "2026-07-08", "valid ISO date"),
        (lambda source: source["period"].update(start="2026-07-09"), "2026-07-08", "must not be after end"),
        (lambda source: None, "bad-date", "market_data_as_of must be a valid ISO date"),
    ],
)
def test_v11_strategy_and_date_semantics_fail_closed(
    tmp_path, mutation, market_as_of, expected
):
    snapshot = _build_from_source(
        tmp_path, mutation, market_data_as_of=market_as_of
    )
    assert snapshot["available"] is False
    assert any(expected in error for error in snapshot["errors"])


def test_diagnosis_dataset_end_must_match_market_cutoff(tmp_path):
    snapshot = _build_from_source(tmp_path, dataset_end="2026-07-07")
    assert snapshot["available"] is False
    assert "diagnosis dataset end must equal market_data_as_of" in snapshot["errors"]


def test_source_state_hash_mismatch_fails_closed(tmp_path):
    snapshot = _build_from_source(
        tmp_path,
        lambda source: source["weights_percent"].update(CASH=20.1),
        recompute_hash=False,
    )
    assert snapshot["available"] is False
    assert "V11 source state hash mismatch" in snapshot["errors"]


def test_diagnosis_payload_must_match_source_file(tmp_path):
    diagnosis = _minimal_diagnosis()
    path = tmp_path / "diagnosis.json"
    path.write_text(json.dumps({"different": True}), encoding="utf-8")
    snapshot = build_v11_current_allocation_snapshot(
        diagnosis,
        market_data_as_of="2026-07-08",
        diagnosis_report_path=path,
    )
    assert snapshot["available"] is False
    assert "diagnosis report payload does not match source file" in snapshot["errors"]


def test_snapshot_loader_missing_file_is_unavailable(tmp_path):
    result = load_v11_current_allocation(tmp_path / "missing.json")
    assert result["available"] is False
    assert result["status"] == "unavailable"


def test_snapshot_loader_malformed_json_is_unavailable(tmp_path):
    path = tmp_path / "malformed.json"
    path.write_text("{bad", encoding="utf-8")
    result = load_v11_current_allocation(path)
    assert result["available"] is False
    assert "invalid" in result["message"]


def test_snapshot_loader_incomplete_schema_is_unavailable(tmp_path):
    path = tmp_path / "incomplete.json"
    path.write_text('{"available": true}', encoding="utf-8")
    result = load_v11_current_allocation(path)
    assert result["available"] is False
    assert "schema is incomplete" in result["message"]


def test_snapshot_loader_preserves_generated_unavailable(tmp_path):
    value = copy.deepcopy(SNAPSHOT)
    value["available"] = False
    value["status"] = "unavailable"
    path = tmp_path / "unavailable.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    result = load_v11_current_allocation(path)
    assert result["available"] is False
    assert result["status"] == "unavailable"


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("diagnosis_report_hash", "diagnosis report hash mismatch"),
        ("source_state_hash", "V11 source state hash mismatch"),
        ("taa_engine_hash", "TAA engine hash mismatch"),
        ("strategy_diagnosis_code_hash", "strategy diagnosis code hash mismatch"),
    ],
)
def test_snapshot_loader_detects_source_drift(tmp_path, field, expected):
    value = copy.deepcopy(SNAPSHOT)
    value["source_integrity"][field] = "0" * 64
    path = tmp_path / "drifted.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    result = load_v11_current_allocation(path, verify_sources=True)
    assert result["available"] is False
    assert result["message"] == "V11 current allocation source drifted; rebuild required"
    assert expected in result["source_integrity"]["errors"]


def test_custom_snapshot_path_skips_live_source_verification(tmp_path):
    value = copy.deepcopy(SNAPSHOT)
    value["source_integrity"]["taa_engine_hash"] = "0" * 64
    path = tmp_path / "historical.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert load_v11_current_allocation(path)["available"] is True


def test_snapshot_write_is_atomic(tmp_path):
    path = tmp_path / "snapshot.json"
    write_v11_current_allocation(SNAPSHOT, path)
    assert json.loads(path.read_text(encoding="utf-8"))["strategy"] == "V11_PRODUCTION_FUSION"
    assert not (tmp_path / ".snapshot.json.tmp").exists()


def test_formal_snapshot_source_verification_passes():
    verification = verify_v11_current_allocation_sources(SNAPSHOT)
    assert verification["verified"] is True
    assert verification["errors"] == []


def test_optional_present_but_invalid_blocks_current_review():
    sources = load_current_market_sources()
    sources["v11_allocation"] = {"available": False, "status": "unavailable"}
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["production_candidate"]["snapshot_present"] is True
    assert report["production_candidate"]["snapshot_valid_or_missing"] is False
    assert report["ready_for_user_review"] is False
    assert "V11 current allocation snapshot is present but invalid" in report["decision_summary"]["blocking_conditions"]


def test_current_loader_rechecks_present_v11_snapshot(monkeypatch, tmp_path):
    current = json.loads(Path("reports/current_market_decision.json").read_text(encoding="utf-8"))
    path = tmp_path / "current.json"
    path.write_text(json.dumps(current), encoding="utf-8")
    monkeypatch.setattr(
        "decision.current_market.report.load_v11_current_allocation",
        lambda: {
            "available": False,
            "status": "unavailable",
            "errors": ["TAA engine hash mismatch"],
        },
    )
    loaded = load_current_market_decision(path, verify_sources=True)
    assert loaded["available"] is False
    assert loaded["ready_for_user_review"] is False
    assert "V11 current allocation snapshot is present but invalid" in loaded["source_hash_verification"]["errors"]


def test_current_decision_integrates_verified_v11_snapshot():
    value = CLIENT.get("/api/decision/current-market").json()
    candidate = value["production_candidate"]
    assert candidate["current_allocation_available"] is True
    assert candidate["snapshot_integrity_verified"] is True
    assert candidate["allocation_source"] == "reports/v11_current_allocation.json"
    assert value["ready_for_user_review"] is True
    assert value["production_actionable"] is False


def test_current_decision_comparison_remains_explanatory_only():
    comparison = CLIENT.get("/api/decision/current-market").json()["comparison"]
    assert comparison["mode"] == "side_by_side_only"
    assert comparison["v11_allocation_available"] is True
    assert comparison["automatic_selection"] is False
    assert comparison["merged_portfolio_created"] is False
    assert comparison["weight_differences"]


def test_v11_api_reads_the_local_snapshot():
    value = CLIENT.get("/api/decision/v11-current-allocation").json()
    assert value["available"] is True
    assert value["source_state_date"] == "2026-07-08"
    assert value["production_actionable"] is False
    assert value["trading_instruction"] is False


def test_v11_api_returns_unavailable_without_500(monkeypatch):
    monkeypatch.setattr(
        "backend.main.load_v11_current_allocation",
        lambda: {"available": False, "status": "unavailable", "errors": ["invalid"]},
    )
    response = CLIENT.get("/api/decision/v11-current-allocation")
    assert response.status_code == 200
    assert response.json()["available"] is False


def test_current_decision_tracks_v11_allocation_freshness():
    value = CLIENT.get("/api/decision/current-market").json()
    assert value["production_candidate"]["allocation_source_as_of"] == "2026-07-08"
    assert not any(
        "V11 current allocation" in error
        for error in value["data_freshness"]["temporal_errors"]
    )


@pytest.mark.parametrize(
    "section",
    [
        "Snapshot Status",
        "V11 Allocation",
        "Equity / Cash Weight",
        "Regime",
        "Risk Budget",
        "Exposure Decision",
        "Selected Assets",
        "Actual Weights vs Target Weights",
        "Canonical Assumptions",
        "Source Integrity",
        "Constraint Checks",
        "Non-Trading Warning",
    ],
)
def test_v11_web_page_sections(section):
    assert section in CLIENT.get("/v11-current-allocation").text


@pytest.mark.parametrize(
    "section",
    [
        "V11 Current Allocation",
        "V11 Equity and Cash",
        "V11 Selected Assets",
        "V11 vs Shadow Weight Differences",
        "V11 Snapshot Integrity",
    ],
)
def test_current_decision_v11_sections(section):
    assert section in CLIENT.get("/current-decision").text


def test_v11_web_page_has_exact_non_trading_warning_and_no_form():
    text = CLIENT.get("/v11-current-allocation").text
    assert "This is an offline V11 model allocation snapshot. It is not an order or trading instruction." in text
    assert "<form" not in text.lower()
    assert "quantity" not in text.lower()
    assert "target price" not in text.lower()


def test_homepage_and_current_decision_link_to_v11_page():
    assert 'href="/v11-current-allocation"' in CLIENT.get("/").text
    assert 'href="/v11-current-allocation"' in CLIENT.get("/current-decision").text


def test_v11_snapshot_module_has_no_backtest_or_fallback_logic():
    source = Path("decision/v11_current/engine.py").read_text(encoding="utf-8")
    assert "run_taa_backtest" not in source
    assert "research_allocation" not in source
    assert "execution_shadow" not in source
    assert "target_weights_percent\"]" not in source.split("allocation =", 1)[1].split("source_integrity", 1)[0]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("market_data_as_of", "bad-date"),
        ("decision_date", "bad-date"),
        ("governance_state_as_of", "bad-date"),
        ("research_source_as_of", "bad-date"),
        ("execution_source_as_of", "bad-date"),
        ("v11_allocation_source_as_of", "bad-date"),
    ],
)
def test_current_decision_invalid_iso_dates_fail_closed(field, value):
    kwargs = {
        "market_data_as_of": "2026-07-08",
        "decision_date": "2026-07-13",
        "governance_state_as_of": "2026-07-13",
        "snapshot_mode": "current_decision_with_lagged_market_data",
        "market_as_of": "2026-07-08",
        "research_date": "2026-06-30",
        "research_source_as_of": "2026-07-08",
        "execution_source_as_of": "2026-07-08",
        "v11_allocation_source_as_of": "2026-07-08",
        "shadow": {"price_as_of_by_proxy": {}},
        "approval_integrity": {},
        "price_verification": {},
    }
    kwargs[field] = value
    result = evaluate_freshness(**kwargs)
    assert result["temporal_status"] == "invalid" or result["status"] == "stale"
    assert any("valid ISO date" in error for error in result["errors"] + result["temporal_errors"])


@pytest.mark.parametrize("field", ["start", "end"])
def test_execution_invalid_iso_period_fails_closed(field):
    sources = load_current_market_sources()
    sources["execution"]["period"][field] = "bad-date"
    report = build_current_market_decision(as_of="2026-07-08", sources=sources)
    assert report["ready_for_user_review"] is False
    assert any(
        f"execution period {field} must be a valid ISO date" in error
        for error in report["execution_validation"]["semantic_errors"]
    )
