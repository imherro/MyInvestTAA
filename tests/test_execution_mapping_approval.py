import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backtest.execution.approval_package import (
    APPROVAL_PACKAGE,
    DECISION_LEDGER,
    SEMANTIC_EVIDENCE,
    TARGET_ASSET_ID,
    load_mapping_approval_package,
    load_mapping_decision_ledger,
)
from backtest.execution.dataset_provenance import (
    AUDIT_REPORT,
    load_price_dataset_manifest,
    verify_price_dataset_manifest,
)
from backtest.execution.drawdown_attribution import drawdown_window
from backtest.execution.models import ExecutionPrice
from backtest.execution.proposal_attribution import build_exact_drawdown_attribution
from engine.asset_registry import load_asset_mappings, load_execution_universe

CLIENT = TestClient(app)
ASSETS = load_execution_universe()
MANIFEST = load_price_dataset_manifest()
AUDIT = json.loads(AUDIT_REPORT.read_text(encoding="utf-8"))
AUDIT_BY_ASSET = {row["asset_id"]: row for row in AUDIT["rows"]}
APPROVAL = json.loads(APPROVAL_PACKAGE.read_text(encoding="utf-8"))
SEMANTIC = json.loads(SEMANTIC_EVIDENCE.read_text(encoding="utf-8"))
LEDGER = json.loads(DECISION_LEDGER.read_text(encoding="utf-8"))


@pytest.mark.parametrize("asset", ASSETS, ids=lambda asset: asset.asset_id)
@pytest.mark.parametrize("field", ["sha256", "row_count", "first_date", "last_date"])
def test_manifest_has_per_file_metadata(asset, field):
    assert MANIFEST["files"][asset.asset_id][field] is not None


@pytest.mark.parametrize("asset", ASSETS, ids=lambda asset: asset.asset_id)
@pytest.mark.parametrize("field", ["row_count", "first_date", "last_date"])
def test_manifest_matches_execution_audit(asset, field):
    assert MANIFEST["files"][asset.asset_id][field] == AUDIT_BY_ASSET[asset.asset_id][field]


@pytest.mark.parametrize("decision", LEDGER["decisions"], ids=lambda row: row["research_asset_id"])
@pytest.mark.parametrize(
    "field",
    [
        "proposed_proxy",
        "status",
        "semantic_quality",
        "statistical_quality",
        "decision_reason",
        "decision_source_report",
        "decided_at",
        "requires_manual_approval",
    ],
)
def test_decision_ledger_entries_are_auditable(decision, field):
    assert field in decision


def test_manifest_is_fully_verified():
    assert verify_price_dataset_manifest(MANIFEST, ASSETS)["provenance_verified"] is True


@pytest.mark.parametrize("field", ["sha256", "row_count", "first_date", "last_date"])
def test_manifest_file_mismatch_fails_provenance(field):
    broken = copy.deepcopy(MANIFEST)
    asset_id = ASSETS[0].asset_id
    broken["files"][asset_id][field] = "broken" if field != "row_count" else -1
    status = verify_price_dataset_manifest(broken, ASSETS)
    assert status["provenance_verified"] is False
    assert any(field in error and asset_id in error for error in status["errors"])


@pytest.mark.parametrize("field", ["row_count", "first_date", "last_date"])
def test_audit_cache_mismatch_fails_provenance(field):
    audit = copy.deepcopy(AUDIT)
    asset_id = ASSETS[0].asset_id
    audit["rows"][0][field] = "broken" if field != "row_count" else -1
    status = verify_price_dataset_manifest(MANIFEST, ASSETS, audit=audit)
    assert status["provenance_verified"] is False
    assert any(field in error and asset_id in error for error in status["errors"])


def test_recovered_drawdown_durations_use_full_underwater_period():
    report = {
        "equity_curve": [
            {"date": "2020-01-01", "value": 1.0},
            {"date": "2020-01-05", "value": 0.8},
            {"date": "2020-01-10", "value": 1.01},
        ]
    }
    result = drawdown_window(report)
    assert result["peak_date"] == "2020-01-01"
    assert result["trough_date"] == "2020-01-05"
    assert result["recovery_date"] == "2020-01-10"
    assert result["decline_days"] == 4
    assert result["underwater_days"] == 9
    assert result["recovery_days"] == 5
    assert result["recovered"] is True
    assert "duration_days" not in result


def test_unrecovered_drawdown_runs_to_report_end():
    report = {
        "equity_curve": [
            {"date": "2020-01-01", "value": 1.0},
            {"date": "2020-01-05", "value": 0.8},
            {"date": "2020-01-10", "value": 0.9},
        ]
    }
    result = drawdown_window(report)
    assert result["recovery_date"] is None
    assert result["recovered"] is False
    assert result["underwater_days"] == 9
    assert result["recovery_days"] == 5


def test_exact_contribution_uses_equity_curve_dates_and_reconciles():
    report = {
        "equity_curve": [
            {"date": "2020-01-01", "value": 1.0},
            {"date": "2020-01-02", "value": 0.9},
            {"date": "2020-01-03", "value": 0.99},
        ],
        "monthly_allocations": [
            {"date": "2020-01-01", "weights": {"ETF": 1.0}}
        ],
    }
    prices = {
        "ETF": [
            ExecutionPrice("ETF", "2020-01-01", 100.0),
            ExecutionPrice("ETF", "2020-01-02", 90.0),
            ExecutionPrice("ETF", "2020-01-03", 99.0),
            ExecutionPrice("ETF", "2020-01-04", 500.0),
        ]
    }
    result = build_exact_drawdown_attribution(
        report,
        prices,
        {"peak_date": "2020-01-01", "trough_date": "2020-01-03"},
    )
    assert result["observation_count"] == 3
    assert result["portfolio_drawdown"] == pytest.approx(-0.01)
    assert result["reconciled_total"] == pytest.approx(-0.01)
    assert result["reconciliation_error"] <= 0.000001
    assert result["method"] == "geometric_linked_daily_contribution"
    assert result["date_alignment"] == "execution_equity_curve"
    assert result["approximate"] is False


@pytest.mark.parametrize(
    "field",
    [
        "research_asset_id",
        "research_asset_name",
        "proposed_proxy",
        "proxy_name",
        "research_index_definition",
        "etf_tracking_index",
        "exposure_comparison",
        "semantic_quality",
        "limitations",
        "requires_manual_approval",
    ],
)
def test_semantic_evidence_has_required_fields(field):
    assert field in SEMANTIC


def test_tracking_index_is_real_index_not_etf_name_inference():
    tracking = SEMANTIC["etf_tracking_index"]
    assert tracking["index_code"] == "990001.CSI"
    assert tracking["index_name"] == "中华交易服务半导体芯片行业指数"
    assert tracking["source"].startswith("https://www.sse.com.cn/")
    assert tracking["snapshot_date"]


def test_research_index_evidence_is_primary_source():
    research = SEMANTIC["research_index_definition"]
    assert research["index_code"] == "931743.CSI"
    assert "csindex.com.cn" in research["source"]
    assert research["snapshot_date"]


def test_component_overlap_is_explicitly_unavailable():
    assert SEMANTIC["exposure_comparison"]["component_overlap_pct"] is None
    assert any("component_overlap_pct" in row for row in SEMANTIC["limitations"])


def test_broader_proxy_exposure_is_disclosed():
    extra = SEMANTIC["exposure_comparison"]["extra_proxy_exposure"]
    assert {"semiconductor design", "semiconductor manufacturing", "semiconductor packaging", "semiconductor testing"} <= set(extra)
    assert SEMANTIC["semantic_quality"] == "acceptable"


def test_user_authorized_mappings_are_approved_for_execution_validation():
    approved = [row for row in LEDGER["decisions"] if row["status"] == "approved_for_execution_validation"]
    assert {row["research_asset_id"] for row in approved} == {
        TARGET_ASSET_ID,
        "931688CNY010.CSI",
        "H00805.CSI",
        "H20590.CSI",
        "H21152.CSI",
    }
    assert all(row["production_approved"] is False for row in approved)


@pytest.mark.parametrize("asset_id", ["931688CNY010.CSI", "H00805.CSI"])
def test_approved_approximate_mappings_retain_execution_only_boundary(asset_id):
    row = next(item for item in LEDGER["decisions"] if item["research_asset_id"] == asset_id)
    assert row["status"] == "approved_for_execution_validation"
    assert row["production_approved"] is False


@pytest.mark.parametrize("asset_id", ["H20590.CSI", "H21152.CSI"])
def test_approved_direct_mappings_retain_execution_only_boundary(asset_id):
    row = next(item for item in LEDGER["decisions"] if item["research_asset_id"] == asset_id)
    assert row["status"] == "approved_for_execution_validation"
    assert row["production_approved"] is False


def test_selective_package_is_931743_only():
    assert APPROVAL["research_asset_id"] == TARGET_ASSET_ID
    assert APPROVAL["proposed_proxy"] == "512760.SH"


def test_selective_package_reconciles_to_one_part_per_million():
    exact = APPROVAL["exact_drawdown_attribution"]["selective_reconciliation"]
    assert exact["reconciliation_error"] <= 0.000001
    assert sum(exact["linked_etf_contributions"].values()) + exact["residual"] == pytest.approx(exact["portfolio_drawdown"], abs=0.000001)


def test_selective_package_uses_correct_drawdown_durations():
    window = APPROVAL["exact_drawdown_attribution"]["selective_window"]
    assert window["decline_days"] == 228
    assert window["underwater_days"] == 1116
    assert window["recovery_days"] == 888
    assert "duration_days" not in window


def test_selective_package_includes_existing_h20007_collision():
    collision = APPROVAL["full_collision_exposure"]
    assert collision["proxy_id"] == "512760.SH"
    assert set(collision["research_asset_ids"]) == {"H20007.CSI", TARGET_ASSET_ID}
    assert collision["max_aggregate_weight"] <= 0.35


@pytest.mark.parametrize(
    ("field", "minimum"),
    [
        ("tradable_weight_coverage_delta", 0.0),
        ("annual_return_delta", -0.02),
        ("max_drawdown_delta", -0.05),
    ],
)
def test_selective_marginal_gate_passes(field, minimum):
    assert APPROVAL["marginal_deltas"][field] >= minimum


def test_package_is_ready_for_explicit_decision_but_not_approved():
    assert APPROVAL["ready_for_explicit_human_decision"] is True
    assert APPROVAL["requires_manual_approval"] is True
    assert APPROVAL["formal_mapping_unchanged"] is True
    assert "approved" not in APPROVAL


def test_formal_mapping_is_now_human_approved_for_execution_validation():
    mapping = next(row for row in load_asset_mappings() if row.research_asset_id == TARGET_ASSET_ID)
    assert mapping.primary_execution_proxy == "512760.SH"
    assert mapping.execution_proxies == ["512760.SH"]
    assert mapping.mapping_quality == "medium"


def test_approval_package_loader_missing(tmp_path):
    assert load_mapping_approval_package(path=tmp_path / "missing.json")["available"] is False


def test_decision_ledger_loader_missing(tmp_path):
    assert load_mapping_decision_ledger(path=tmp_path / "missing.json")["available"] is False
