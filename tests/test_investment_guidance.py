from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import backend.main as main_module
from release.orchestrator import load_release_json


ROOT = Path(__file__).resolve().parents[1]
CLIENT = TestClient(main_module.app)
DECISION = load_release_json("current_market_decision.json")
EXECUTION = load_release_json("execution_backtest_report.json")


def _api() -> dict[str, Any]:
    response = CLIENT.get("/api/investment-guidance")
    assert response.status_code == 200
    return response.json()


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _sha256(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_01_current_decision_returns_200_with_five_primary_links():
    response = CLIENT.get("/current-decision")
    assert response.status_code == 200
    assert response.text.count('class="primary-nav"') == 1
    nav = response.text.split('class="primary-nav"', 1)[1].split("</nav>", 1)[0]
    assert nav.count("<a ") == 5


def test_02_api_exposes_formal_dates_and_non_production_boundary():
    payload = _api()
    assert payload["available"] is True
    assert payload["decision_date"] == DECISION["decision_date"]
    assert payload["market_data_as_of"] == DECISION["market_data_as_of"]
    assert payload["production_actionable"] is False


def test_03_api_current_guidance_fields_equal_committed_decision():
    payload = _api()
    assert payload["market_state"] == {
        key: DECISION["market_state"][key]
        for key in ("regime", "risk_level", "confidence")
    }
    assert payload["production_candidate"] == {
        key: DECISION["production_candidate"][key]
        for key in ("equity_weight", "cash_weight")
    }


def test_04_release_failure_is_fail_closed_for_api_and_page(monkeypatch):
    def unavailable(name: str) -> dict[str, Any]:
        if name == "system_acceptance_report.json":
            return {"available": False, "blocking_errors": ["broken"]}
        return load_release_json(name)

    monkeypatch.setattr(main_module, "load_release_json", unavailable)
    payload = CLIENT.get("/api/investment-guidance").json()
    assert payload["available"] is False
    assert "strategy_equity" not in payload
    html = CLIENT.get("/current-decision").text
    assert "当前正式投资指导不可用" in html
    assert "Execution V1 策略净值" not in html


def test_05_strategy_equity_is_pointwise_identical_to_execution_v1():
    payload = _api()
    assert payload["strategy_equity"]["points"] == EXECUTION["equity_curve"]
    assert payload["strategy_equity"]["period"] == EXECUTION["period"]
    assert payload["strategy_equity"]["metrics"] == EXECUTION["metrics"]


def test_06_510500_benchmark_is_aligned_with_execution_curve():
    payload = _api()
    benchmark = payload["benchmark"]
    assert benchmark["asset_id"] == "510500.SH"
    assert benchmark["available"] is True
    assert benchmark["return_basis"] == "qfq"
    assert [row["date"] for row in benchmark["points"]] == [
        row["date"] for row in payload["strategy_equity"]["points"]
    ]
    html = CLIENT.get("/current-decision").text
    assert 'data-series="510500.SH"' in html
    assert "data-crosshair" in html
    assert 'class="chart-tooltip"' in html


def test_07_new_module_has_no_network_cdn_or_external_price_source():
    source = (ROOT / "backend/investment_guidance.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "data/execution_prices/510500_sh.json",
        "http://",
        "https://",
        "tushare",
        "requests",
        "urlopen",
    )
    assert all(item not in source for item in forbidden)


def test_08_allocation_dates_come_only_from_formal_allocation_arrays():
    payload = _api()
    formal_mapped_dates = [row["date"] for row in EXECUTION["monthly_allocations"]]
    formal_research_dates = [
        row["date"] for row in EXECUTION["source_research_allocations"]
    ]
    actual_dates = [row["allocation_date"] for row in payload["allocation_records"]]
    assert actual_dates == formal_mapped_dates == formal_research_dates


def test_09_allocation_records_expose_only_provable_fields():
    payload = _api()
    expected = {
        "allocation_date",
        "signal_observation_date",
        "target_allocation_date",
        "next_execution_date",
        "record_type",
        "research_target_weights",
        "mapped_target_weights",
        "mapped_target_cash_weight",
        "cash_breakdown",
    }
    assert len(payload["recent_allocation_records"]) == 12
    assert all(set(row) == expected for row in payload["allocation_records"])


def test_10_weight_chart_is_exact_mapped_target_series_without_aggregation():
    payload = _api()
    chart = payload["allocation_chart"]
    expected_assets = sorted(
        {
            asset_id
            for row in EXECUTION["monthly_allocations"]
            for asset_id in row["weights"]
        },
        key=lambda asset_id: (asset_id == "CASH", asset_id),
    )
    assert chart["series_type"] == "mapped_monthly_target_weights"
    assert chart["actual_holding_series"] is False
    assert [series["asset_id"] for series in chart["series"]] == expected_assets
    assert chart["dates"] == [row["date"] for row in EXECUTION["monthly_allocations"]]
    for series in chart["series"]:
        assert series["values"] == [
            row["weights"].get(series["asset_id"], 0.0)
            for row in EXECUTION["monthly_allocations"]
        ]


def test_11_non_executable_assets_and_reasons_are_unchanged():
    assert _api()["non_executable_assets"] == EXECUTION["non_executable_assets"]


def test_12_execution_validation_is_global_formal_status():
    validation = _api()["execution_validation"]
    formal = EXECUTION["decision"]
    assert validation["ready"] == formal["ready_for_execution_validation"]
    assert validation["reasons"] == formal["reasons"]
    assert validation["reason_details"] == formal["reason_details"]
    assert "status" not in _all_keys(_api()["allocation_records"])


def test_13_api_contains_no_trading_instruction_fields():
    forbidden = {
        "order",
        "quantity",
        "shares",
        "trade_amount",
        "target_price",
        "buy_price",
        "sell_price",
    }
    assert _all_keys(_api()).isdisjoint(forbidden)


def test_14_page_preserves_boundaries_and_has_no_execution_controls():
    html = CLIENT.get("/current-decision").text
    for phrase in ("用于人工判断", "不会生成订单", "非交易指令"):
        assert phrase in html
    assert "<form" not in html.lower()
    assert 'name="viewport"' in html


def test_15_protected_baselines_and_legacy_v2_freezes_are_unchanged():
    v2 = json.loads((ROOT / "reports/execution_backtest_v2_report.json").read_text())
    b2 = json.loads((ROOT / "reports/execution_v2_b2_cost_COMMITTED.json").read_text())
    manifest = load_release_json("release_manifest.json")
    protected = manifest["protected_file_hashes"]
    assert protected["verified"] is True
    for item in protected["files"]:
        assert item["baseline_sha256"] == item["actual_sha256"]
        assert _sha256(item["path"]) == item["actual_sha256"]
    execution_artifact = next(
        row for row in manifest["artifacts"] if row["path"] == "execution_backtest_report.json"
    )
    assert execution_artifact["sha256"] == _sha256("reports/release/current/execution_backtest_report.json")
    assert v2["b1_golden_freeze"]["actual_semantic_sha256"] == (
        "612062e915811ce6588ba276f339d819d9fe3e164127247546e262f7984e2e55"
    )
    assert b2["output_set_hash"] == "f7be8bb0358b627fab431d105f806023955d4435292245dcf7fe4ab99ea99252"
    assert manifest["release_id"].startswith("taa-")
