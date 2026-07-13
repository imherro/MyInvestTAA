import copy
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backtest.execution.approval_package import APPROVAL_PACKAGE, TARGET_ASSET_ID
from backtest.execution.mapping_application import (
    APPROVAL_RECORD,
    apply_human_approved_mapping,
    load_mapping_approval_record,
    validate_approval_record,
)
from backtest.execution.models import ExecutionPrice
from backtest.execution.proposal_attribution import build_exact_drawdown_attribution
from backtest.execution.report import load_execution_backtest_report
from backtest.execution.shadow_portfolio import (
    CASH_BREAKDOWN_KEYS,
    build_execution_aware_shadow_portfolio,
)
from backtest.execution.shadow_report import (
    SHADOW_PORTFOLIO_REPORT,
    load_execution_aware_shadow_portfolio,
)
from engine.asset_registry import load_asset_mappings
from engine.asset_registry.models import AssetMapping

CLIENT = TestClient(app)
RECORD = load_mapping_approval_record()
PACKAGE = json.loads(APPROVAL_PACKAGE.read_text(encoding="utf-8"))
SHADOW = load_execution_aware_shadow_portfolio()
EXECUTION = load_execution_backtest_report()
LEDGER = json.loads(
    Path("data/universe/execution_mapping_decision_ledger.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize(
    "field",
    [
        "research_asset_id",
        "approved_proxy",
        "approved_mapping_quality",
        "decision_type",
        "explicit_approval_input",
        "decision_date",
        "source_package",
        "package_hash",
        "mapping_before_hash",
        "mapping_after_hash",
        "changed_asset_ids",
        "mapping_change",
        "limitations",
        "production_approved",
    ],
)
def test_approval_record_is_complete(field):
    assert field in RECORD


@pytest.mark.parametrize(
    "decision", LEDGER["decisions"], ids=lambda row: row["research_asset_id"]
)
@pytest.mark.parametrize(
    "field",
    [
        "research_asset_id",
        "proposed_proxy",
        "status",
        "decision_reason",
        "requires_manual_approval",
    ],
)
def test_post_approval_ledger_remains_auditable(decision, field):
    assert field in decision


@pytest.mark.parametrize(
    "row", SHADOW["mapping_explanations"], ids=lambda row: row["research_asset_id"]
)
@pytest.mark.parametrize(
    "field",
    [
        "research_asset_id",
        "research_weight",
        "destination",
        "reason",
    ],
)
def test_shadow_mapping_explanations_are_auditable(row, field):
    assert field in row


def test_approval_record_hash_matches_approved_package():
    assert RECORD["package_hash"] == hashlib.sha256(APPROVAL_PACKAGE.read_bytes()).hexdigest()
    assert validate_approval_record(RECORD)["approval_record_verified"] is True


def test_approval_record_never_grants_production():
    assert RECORD["decision_type"] == "explicit_human_approval"
    assert RECORD["explicit_approval_input"] == "approved"
    assert RECORD["approved_mapping_quality"] == "medium"
    assert RECORD["production_approved"] is False


def test_mapping_hashes_match_recorded_files():
    current = hashlib.sha256(Path("data/universe/asset_mapping.json").read_bytes()).hexdigest()
    assert current == RECORD["mapping_after_hash"]
    assert RECORD["mapping_before_hash"] != RECORD["mapping_after_hash"]


def test_only_target_mapping_changed_in_approval_record():
    assert RECORD["changed_asset_ids"] == [TARGET_ASSET_ID]
    assert RECORD["mapping_change"]["before"]["primary_execution_proxy"] is None
    assert RECORD["mapping_change"]["after"]["primary_execution_proxy"] == "512760.SH"


def test_formal_target_mapping_matches_approval_record():
    mapping = next(
        row for row in load_asset_mappings() if row.research_asset_id == TARGET_ASSET_ID
    )
    assert mapping.as_dict() == RECORD["mapping_change"]["after"]


def test_only_target_ledger_entry_is_approved():
    approved = [
        row
        for row in LEDGER["decisions"]
        if row["status"] == "approved_for_execution_validation"
    ]
    assert [row["research_asset_id"] for row in approved] == [TARGET_ASSET_ID]
    assert approved[0]["production_approved"] is False


@pytest.mark.parametrize(
    ("asset_id", "status"),
    [
        ("931688CNY010.CSI", "research_only"),
        ("H00805.CSI", "research_only"),
        ("H20590.CSI", "rejected_proxy"),
        ("H21152.CSI", "rejected_proxy"),
    ],
)
def test_other_frozen_ledger_states_are_unchanged(asset_id, status):
    row = next(
        item for item in LEDGER["decisions"] if item["research_asset_id"] == asset_id
    )
    assert row["status"] == status
    assert row.get("production_approved") is not True


def test_execution_report_uses_formal_mapping_registry():
    assert EXECUTION["data_provider"] == "tushare"
    assert EXECUTION["mapping_registry_version"] == RECORD["mapping_after_hash"]
    assert EXECUTION["approval_record_verification"]["approval_record_verified"] is True
    assert EXECUTION["approved_mapping_records"][0]["research_asset_id"] == TARGET_ASSET_ID
    assert EXECUTION["approved_mapping_records"][0]["production_approved"] is False


def test_execution_readiness_remains_honestly_false():
    assert EXECUTION["decision"]["ready_for_execution_validation"] is False
    assert "tradable weight coverage is below 70%" in EXECUTION["decision"]["reasons"]
    assert EXECUTION["mapping_summary"]["tradable_weight_coverage"] == pytest.approx(0.691469)


def test_mapping_improvement_respects_frozen_decisions():
    report = json.loads(
        Path("reports/execution_mapping_improvement_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(report["frozen_assets"]) == {
        "931688CNY010.CSI",
        "H00805.CSI",
        "H20590.CSI",
        "H21152.CSI",
    }
    for row in report["recommended_actions"]:
        if row["research_asset_id"] in report["frozen_assets"]:
            assert "frozen" in row["suggestion"]


def test_shadow_current_output_is_ratio_only():
    assert SHADOW["status"] == "shadow_only"
    assert SHADOW["production_approved"] is False
    assert SHADOW["source_allocation_date"] == "2026-06-30"
    assert SHADOW["data_as_of"] == "2026-07-08"
    assert SHADOW["execution_weights"] == {
        "510500.SH": 0.25,
        "512760.SH": 0.1,
        "588000.SH": 0.25,
        "CASH": 0.4,
    }


@pytest.mark.parametrize("field", CASH_BREAKDOWN_KEYS)
def test_shadow_has_each_cash_breakdown_field(field):
    assert field in SHADOW["cash_breakdown"]


def test_shadow_cash_breakdown_is_explainable():
    assert SHADOW["cash_breakdown"] == {
        "research_cash": 0.3,
        "unmapped_cash": 0.0,
        "research_only_cash": 0.1,
        "rejected_proxy_cash": 0.0,
        "low_quality_proxy_cash": 0.0,
        "missing_price_cash": 0.0,
    }
    assert SHADOW["constraint_checks"]["weight_sum"] == pytest.approx(1.0)
    assert SHADOW["constraint_checks"]["violations"] == []


def test_shadow_keeps_v11_boundary_explicit():
    assert any("V11 remains" in warning for warning in SHADOW["warnings"])
    assert all(record["production_approved"] is False for record in SHADOW["approved_mapping_records"])


def test_shadow_contains_no_order_or_position_size_fields():
    forbidden = {"order", "orders", "shares", "quantity", "quantities", "target_price", "trade_amount"}

    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()), set())
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value), set())
        return set()

    assert not (forbidden & keys(SHADOW))


def _application_files(tmp_path):
    mapping_path = tmp_path / "asset_mapping.json"
    package_path = tmp_path / "approval_package.json"
    ledger_path = tmp_path / "ledger.json"
    record_path = tmp_path / "record.json"
    mappings = [
        copy.deepcopy(RECORD["mapping_change"]["before"]),
        {
            "research_asset_id": "OTHER",
            "research_asset_name": "Other",
            "primary_execution_proxy": "ETF",
            "execution_proxies": ["ETF"],
            "mapping_quality": "high",
            "notes": "unchanged",
        },
    ]
    mapping_path.write_text(json.dumps(mappings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    package_path.write_text(json.dumps(PACKAGE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ledger = {
        "available": True,
        "decisions": [
            {
                "research_asset_id": TARGET_ASSET_ID,
                "proposed_proxy": "512760.SH",
                "status": "pending_explicit_human_approval",
                "decision_reason": "pending",
                "requires_manual_approval": True,
            },
            {
                "research_asset_id": "OTHER",
                "proposed_proxy": "ETF",
                "status": "research_only",
                "decision_reason": "frozen",
                "requires_manual_approval": True,
            },
        ],
    }
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    expected_hash = hashlib.sha256(mapping_path.read_bytes()).hexdigest()
    return mapping_path, package_path, ledger_path, record_path, expected_hash


def test_application_requires_explicit_approval(tmp_path):
    files = _application_files(tmp_path)
    before = files[0].read_bytes()
    with pytest.raises(ValueError, match="explicit human approval"):
        apply_human_approved_mapping(
            explicit_approval="rejected",
            expected_mapping_hash=files[4],
            decision_date="2026-07-13",
            mapping_path=files[0], package_path=files[1], ledger_path=files[2], record_path=files[3],
        )
    assert files[0].read_bytes() == before


def test_application_rejects_full_mapping_hash_mismatch(tmp_path):
    files = _application_files(tmp_path)
    with pytest.raises(ValueError, match="baseline hash mismatch"):
        apply_human_approved_mapping(
            explicit_approval="approved",
            expected_mapping_hash="0" * 64,
            decision_date="2026-07-13",
            mapping_path=files[0], package_path=files[1], ledger_path=files[2], record_path=files[3],
        )
    assert not files[3].exists()


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("exact_drawdown_attribution", "selective_reconciliation", "residual"), 0.1, "residual exceeds"),
        (("exact_drawdown_attribution", "selective_reconciliation", "reconciliation_error"), 0.1, "reconciliation error"),
        (("exact_drawdown_attribution", "selective_reconciliation", "approximate"), True, "attribution is approximate"),
        (("semantic_evidence", "semantic_quality"), "weak", "semantic quality"),
        (("proposed_proxy",), "OTHER", "proxy mismatch"),
    ],
)
def test_application_rejects_invalid_approval_package(tmp_path, path, value, message):
    files = _application_files(tmp_path)
    package = json.loads(files[1].read_text(encoding="utf-8"))
    target = package
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    files[1].write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        apply_human_approved_mapping(
            explicit_approval="approved",
            expected_mapping_hash=files[4],
            decision_date="2026-07-13",
            mapping_path=files[0], package_path=files[1], ledger_path=files[2], record_path=files[3],
        )


def test_application_atomically_changes_only_target(tmp_path):
    files = _application_files(tmp_path)
    before = json.loads(files[0].read_text(encoding="utf-8"))
    record = apply_human_approved_mapping(
        explicit_approval="approved",
        expected_mapping_hash=files[4],
        decision_date="2026-07-13",
        mapping_path=files[0], package_path=files[1], ledger_path=files[2], record_path=files[3],
    )
    after = json.loads(files[0].read_text(encoding="utf-8"))
    assert [row["research_asset_id"] for old, row in zip(before, after) if old != row] == [TARGET_ASSET_ID]
    assert after[1] == before[1]
    assert record["changed_asset_ids"] == [TARGET_ASSET_ID]
    assert not (tmp_path / ".asset_mapping.json.tmp").exists()


def test_application_rolls_back_mapping_and_ledger_when_record_write_fails(tmp_path, monkeypatch):
    import backtest.execution.mapping_application as application

    files = _application_files(tmp_path)
    mapping_before = files[0].read_bytes()
    ledger_before = files[2].read_bytes()
    original_write = application._atomic_write_text

    def fail_record(path, value):
        if path == files[3]:
            raise OSError("simulated record failure")
        return original_write(path, value)

    monkeypatch.setattr(application, "_atomic_write_text", fail_record)
    with pytest.raises(OSError, match="simulated record failure"):
        apply_human_approved_mapping(
            explicit_approval="approved",
            expected_mapping_hash=files[4],
            decision_date="2026-07-13",
            mapping_path=files[0], package_path=files[1], ledger_path=files[2], record_path=files[3],
        )
    assert files[0].read_bytes() == mapping_before
    assert files[2].read_bytes() == ledger_before
    assert not files[3].exists()


def test_large_attribution_residual_is_marked_approximate():
    report = {
        "equity_curve": [
            {"date": "2020-01-01", "value": 1.0},
            {"date": "2020-01-02", "value": 1.1},
        ],
        "monthly_allocations": [
            {"date": "2020-01-01", "weights": {"ETF": 1.0}}
        ],
    }
    prices = {
        "ETF": [
            ExecutionPrice("ETF", "2020-01-01", 1.0),
            ExecutionPrice("ETF", "2020-01-02", 1.0),
        ]
    }
    exact = build_exact_drawdown_attribution(
        report,
        prices,
        {"peak_date": "2020-01-01", "trough_date": "2020-01-02"},
    )
    assert exact["reconciliation_error"] <= 0.000001
    assert abs(exact["residual"]) > 0.000001
    assert exact["approximate"] is True


def _shadow_fixture(weights, mappings, ledger=None, missing=None):
    date = "2026-01-30"
    research = {
        "available": True,
        "strategy": "RESEARCH_TAA_MVP",
        "period": {"end": date},
        "monthly_allocations": [
            {"date": "2025-12-31", "weights": {"CASH": 1.0}},
            {"date": date, "weights": weights},
        ],
    }
    prices = {}
    for mapping in mappings:
        if mapping.primary_execution_proxy and mapping.primary_execution_proxy not in (missing or set()):
            prices[mapping.primary_execution_proxy] = [
                ExecutionPrice(mapping.primary_execution_proxy, date, 1.0)
            ]
    provenance = {"provenance_verified": True, "provider": "tushare", "return_basis": "qfq", "end": date, "asset_count": len(prices)}
    return build_execution_aware_shadow_portfolio(
        research,
        mappings,
        prices,
        provenance,
        {"decisions": ledger or []},
        {"research_asset_id": TARGET_ASSET_ID, "approved_proxy": "512760.SH", "approved_mapping_quality": "medium"},
    )


def test_shadow_uses_latest_completed_allocation_and_aggregates_proxy():
    mappings = [
        AssetMapping("A", "A", "ETF", ["ETF"], "high"),
        AssetMapping("B", "B", "ETF", ["ETF"], "medium"),
    ]
    report = _shadow_fixture({"A": 0.2, "B": 0.3, "CASH": 0.5}, mappings)
    assert report["source_allocation_date"] == "2026-01-30"
    assert report["execution_weights"] == {"CASH": 0.5, "ETF": 0.5}


@pytest.mark.parametrize(
    ("quality", "status", "expected_cash"),
    [
        ("none", None, "unmapped_cash"),
        ("low", None, "low_quality_proxy_cash"),
        ("medium", "research_only", "research_only_cash"),
        ("medium", "rejected_proxy", "rejected_proxy_cash"),
    ],
)
def test_shadow_routes_ineligible_research_weight_to_named_cash(quality, status, expected_cash):
    proxy = None if quality == "none" else "ETF"
    mappings = [AssetMapping("A", "A", proxy, [proxy] if proxy else [], quality)]
    ledger = [{"research_asset_id": "A", "status": status}] if status else []
    report = _shadow_fixture({"A": 0.4, "CASH": 0.6}, mappings, ledger)
    assert report["cash_breakdown"][expected_cash] == pytest.approx(0.4)
    assert report["execution_weights"] == {"CASH": 1.0}


def test_shadow_routes_missing_as_of_price_to_cash():
    mappings = [AssetMapping("A", "A", "ETF", ["ETF"], "high")]
    report = _shadow_fixture({"A": 0.4, "CASH": 0.6}, mappings, missing={"ETF"})
    assert report["cash_breakdown"]["missing_price_cash"] == pytest.approx(0.4)
    assert report["execution_weights"] == {"CASH": 1.0}


def test_shadow_records_35_percent_violation_without_reallocation():
    mappings = [AssetMapping("A", "A", "ETF", ["ETF"], "high")]
    report = _shadow_fixture({"A": 0.6, "CASH": 0.4}, mappings)
    assert report["execution_weights"]["ETF"] == pytest.approx(0.6)
    assert report["constraint_checks"]["violations"] == [
        {"asset_id": "ETF", "weight": 0.6, "limit": 0.35}
    ]


def test_shadow_report_loader_missing(tmp_path):
    assert load_execution_aware_shadow_portfolio(tmp_path / "missing.json")["available"] is False


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/research/execution-aware-shadow-portfolio",
        "/api/research/execution-mapping-approval-record",
    ],
)
def test_task_032_read_only_apis(endpoint):
    response = CLIENT.get(endpoint)
    assert response.status_code == 200
    assert response.json()["available"] is True


def test_shadow_api_missing_report_does_not_500(monkeypatch):
    monkeypatch.setattr(
        "backend.main.load_execution_aware_shadow_portfolio",
        lambda: {"available": False, "message": "missing"},
    )
    response = CLIENT.get("/api/research/execution-aware-shadow-portfolio")
    assert response.status_code == 200
    assert response.json()["available"] is False


@pytest.mark.parametrize(
    "section",
    [
        "Source Research Allocation",
        "Research Weights",
        "Executable ETF Weights",
        "Cash Breakdown",
        "Mapping Explanations",
        "Frozen Research-Only Assets",
        "Constraint Checks",
        "Data Provenance",
        "Shadow Status",
        "V11 Boundary",
    ],
)
def test_shadow_page_sections(section):
    assert section in CLIENT.get("/shadow-portfolio").text


def test_shadow_page_has_required_warning_and_unified_shell():
    text = CLIENT.get("/shadow-portfolio").text
    assert "This is an experimental execution-aware shadow allocation. It is not a production portfolio or trading instruction." in text
    assert "https://invest.okbbc.com/header.js" in text
    assert "https://invest.okbbc.com/footer.js" in text


@pytest.mark.parametrize("page", ["/", "/research-backtest", "/execution-backtest"])
def test_existing_pages_link_to_shadow_portfolio(page):
    assert 'href="/shadow-portfolio"' in CLIENT.get(page).text
