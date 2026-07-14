from copy import deepcopy
import hashlib
import json
import math
import os

import pytest

from backtest.execution.data_loader import load_execution_price_dataset
from backtest.execution.v2 import cost_validation
from backtest.execution.v2.calendar import load_trade_calendar
from backtest.execution.v2.cost_domain import VALUE_TOLERANCE
from backtest.execution.v2.costs import POLICY_PATH, execute_targets_with_costs, load_cost_policy
from backtest.execution.v2.engine import run_execution_backtest_v2
from backtest.execution.v2.investability import load_instrument_metadata
from backtest.execution.v2.report import COMMITTED as B1_COMMITTED, load_execution_v2_report
from backtest.execution.report import load_execution_backtest_report
from backtest.execution.v2.scenario import (
    ENGINE_SOURCE_PATHS,
    STRATEGY,
    build_expected_cost_run_identity,
    run_cost_scenario,
)
from engine.asset_registry import load_asset_mappings, load_execution_universe


B1 = load_execution_v2_report()
ASSETS = load_execution_universe()
PRICES = load_execution_price_dataset(ASSETS)
MAPPINGS = load_asset_mappings()
CALENDAR = load_trade_calendar()
METADATA = load_instrument_metadata()
V1 = load_execution_backtest_report()
POLICY = load_cost_policy()
B1_OUTPUT_SET_HASH = json.loads(B1_COMMITTED.read_text(encoding="utf-8"))["output_set_hash"]
REPORT = cost_validation.load_cost_report()
LEDGER = json.loads(cost_validation.LEDGER.read_text(encoding="utf-8"))
COMPARISON = json.loads(cost_validation.COMPARISON.read_text(encoding="utf-8"))


def _atomic_test_write(target, content):
    temporary = target.with_name(f".{target.name}.test-replacement")
    temporary.write_bytes(content)
    os.replace(temporary, target)


def test_cost_policy_is_explicit_verified_zero_cash_research_assumption():
    assert POLICY.policy_id == "EXECUTION_V2_COST_POLICY_V1"
    assert POLICY.scenario_id == "base_cost"
    assert POLICY.commission_buy_bps == POLICY.commission_sell_bps == 10
    assert POLICY.slippage_buy_bps == POLICY.slippage_sell_bps == 5
    raw = json.loads((cost_validation.ROOT / "config/execution_v2_cost_policy.json").read_text(encoding="utf-8"))
    assert raw["cash_yield"] == 0
    assert "research" in raw["assumption_source"].lower()
    assert POLICY.evidence_status == "research_assumption_not_market_verified"
    assert POLICY.production_approved is False


@pytest.mark.parametrize("field,value", [("verified", False), ("cash_yield", 0.01)])
def test_invalid_policy_contract_fails_closed(tmp_path, field, value):
    raw = json.loads((cost_validation.ROOT / "config/execution_v2_cost_policy.json").read_text(encoding="utf-8"))
    raw[field] = value
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="contract"):
        load_cost_policy(path)


def test_negative_or_nonfinite_bps_fail_closed(tmp_path):
    raw = json.loads((cost_validation.ROOT / "config/execution_v2_cost_policy.json").read_text(encoding="utf-8"))
    raw["commission"]["buy_bps"] = -1
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cost_policy(path)
    raw["commission"]["buy_bps"] = math.inf
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cost_policy(path)


def test_single_buy_cost_is_exact():
    positions = {}
    cash, rows, constraint = execute_targets_with_costs(
        date_value="2026-01-01", parent_event_id="signal", pending_adjustment_id=None,
        positions=positions, cash=1.0, targets={"510300.SH": 0.25}, policy=POLICY,
        event_pre_trade_nav=1.0,
    )
    row = rows[0]
    assert row["direction"] == "buy"
    assert row["gross_traded_notional"] == 0.25
    assert row["commission_cost"] == 0.00025
    assert row["slippage_cost"] == 0.000125
    assert row["tax_cost"] == 0
    assert row["total_cost"] == 0.000375
    assert cash == pytest.approx(0.749625)
    assert constraint["cost_constrained_target_residual"] == 0


def test_single_sale_to_zero_has_sell_ledger():
    positions = {"510300.SH": 0.25}
    cash, rows, _ = execute_targets_with_costs(
        date_value="2026-01-01", parent_event_id="signal", pending_adjustment_id=None,
        positions=positions, cash=0.75, targets={"510300.SH": 0.0}, policy=POLICY,
        event_pre_trade_nav=1.0,
    )
    assert rows[0]["direction"] == "sell"
    assert rows[0]["executed_post_trade_value"] == 0
    assert "510300.SH" not in positions
    assert cash == pytest.approx(0.999625)
    assert rows[0]["pre_trade_cash"] == 0.75
    assert rows[0]["post_trade_cash"] == 0.999625
    assert rows[0]["sequence_number"] == 1


def test_unchanged_target_and_zero_notional_have_no_ledger():
    positions = {"510300.SH": 0.25}
    cash, rows, _ = execute_targets_with_costs(
        date_value="2026-01-01", parent_event_id="signal", pending_adjustment_id=None,
        positions=positions, cash=0.75, targets={"510300.SH": 0.25}, policy=POLICY,
        event_pre_trade_nav=1.0,
    )
    assert rows == []
    assert cash == 0.75


def test_aggregated_single_etf_target_unchanged_has_no_cost():
    positions = {"512760.SH": 0.2}
    cash, rows, constraint = execute_targets_with_costs(
        date_value="2026-01-01", parent_event_id="aggregated-signal",
        pending_adjustment_id=None, positions=positions, cash=0.8,
        targets={"512760.SH": 0.2}, policy=POLICY, event_pre_trade_nav=1.0,
    )
    assert rows == []
    assert cash == 0.8
    assert constraint["requested_buy_notional"] == 0


def test_cash_shortage_scales_buys_without_borrowing():
    positions = {}
    cash, rows, constraint = execute_targets_with_costs(
        date_value="2026-01-01", parent_event_id="signal", pending_adjustment_id=None,
        positions=positions, cash=0.1, targets={"510300.SH": 0.1, "510500.SH": 0.1}, policy=POLICY,
        event_pre_trade_nav=0.1,
    )
    assert cash >= 0
    assert constraint["buy_scale"] < 1
    assert constraint["cost_constrained_target_residual"] > 0
    assert sum(row["gross_traded_notional"] + row["total_cost"] for row in rows) == pytest.approx(0.1)
    assert rows[0]["post_trade_cash"] == rows[1]["pre_trade_cash"]
    assert rows[-1]["post_trade_cash"] == 0


def test_zero_cost_scenario_is_pointwise_b1_golden(tmp_path):
    raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    raw["scenario_id"] = "zero_cost_test"
    for category in ("commission", "slippage", "tax"):
        raw[category]["buy_bps"] = 0
        raw[category]["sell_bps"] = 0
    zero_path = tmp_path / "zero-cost-policy.json"
    zero_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    zero = load_cost_policy(zero_path)
    report, ledger, _ = run_cost_scenario(
        B1, PRICES, zero, b1_output_set_hash=B1_OUTPUT_SET_HASH,
        cost_policy_path=zero_path,
    )
    assert report["net_cost_curve"] == B1["equity_curve_net"]
    assert report["metrics_net_cost"] == B1["metrics_net"]
    assert ledger["rows"]
    assert all(row["total_cost"] == 0 for row in ledger["rows"])
    assert zero.policy_sha256 == hashlib.sha256(zero_path.read_bytes()).hexdigest()
    assert B1["b1_golden_freeze"]["verified"] is True


def test_base_cost_scenario_has_expected_direction_and_grid():
    assert REPORT["available"] is True
    assert REPORT["production_actionable"] is False
    assert REPORT["eligible_to_replace_v1"] is False
    assert REPORT["validation"]["cash_yield_zero"] is True
    assert REPORT["net_cost_curve"][-1]["value"] < B1["equity_curve_net"][-1]["value"]
    assert COMPARISON["date_grid_equal"] is True
    assert [row["date"] for row in REPORT["net_cost_curve"]] == [row["date"] for row in B1["equity_curve_net"]]


def test_cost_ledger_and_daily_bridge_reconcile():
    ledger_total = round(sum(row["total_cost"] for row in LEDGER["rows"]), 10)
    daily_total = round(sum(row["transaction_cost"] for row in REPORT["daily_portfolio_states"]), 10)
    assert ledger_total == daily_total == REPORT["cost_attribution"]["total_cost"]
    assert all(abs(row["closing_nav"] - (row["pre_trade_nav"] - row["transaction_cost"])) < 2e-8 for row in REPORT["daily_portfolio_states"])
    curve = [row["value"] for row in REPORT["cumulative_cost_curve"]]
    assert curve == sorted(curve)


def test_every_ledger_row_has_policy_and_actual_notional():
    assert LEDGER["rows"]
    for row in LEDGER["rows"]:
        assert row["gross_traded_notional"] > 0
        assert row["policy_id"] == POLICY.policy_id
        assert row["policy_sha256"] == POLICY.policy_sha256
        assert row["direction"] in {"buy", "sell"}


def test_cost_run_id_is_recomputed_from_policy_scenario_and_b1():
    expected = build_expected_cost_run_identity(
        verified_b1=B1,
        b1_marker=json.loads(B1_COMMITTED.read_text(encoding="utf-8")),
        cost_policy_path=POLICY_PATH,
        master_dates=[row["date"] for row in B1["daily_portfolio_states"]],
        strategy=STRATEGY,
        source_paths=ENGINE_SOURCE_PATHS,
    )
    assert REPORT["run_id"] == expected["run_id"]
    assert REPORT["run_identity_components"] == expected["components"]
    components = REPORT["run_identity_components"]
    assert components["cost_policy_hash"] == POLICY.policy_sha256
    assert components["scenario_id"] == POLICY.scenario_id
    assert components["b1_output_set_hash"] == B1_OUTPUT_SET_HASH
    assert set(components["engine_source_hashes"]) == {
        "backtest/execution/v2/cost_domain.py",
        "backtest/execution/v2/costs.py",
        "backtest/execution/v2/scenario.py",
    }


def test_comparison_declares_turnover_denominator_and_calendar_return_drag():
    assert COMPARISON["turnover_denominator"] == "initial_portfolio_nav_1.0"
    assert COMPARISON["turnover_notional_initial_nav_units"] > 0
    assert COMPARISON["elapsed_calendar_annual_return_difference_percentage_points"] < 0


def test_pending_adjustment_cost_is_booked_only_on_recovery_date():
    prices = deepcopy(PRICES)
    prices["510300.SH"] = [row for row in prices["510300.SH"] if row.date != "2021-03-01"]
    research = {
        "period": {"start": "2021-02-18", "end": "2021-03-03"},
        "monthly_allocations": [
            {"date": "2021-02-19", "weights": {"H00300.CSI": 0.25, "CASH": 0.75}},
            {"date": "2021-02-26", "weights": {"CASH": 1.0}},
        ],
    }
    synthetic_b1 = run_execution_backtest_v2(
        research, prices, MAPPINGS, ASSETS, CALENDAR, METADATA,
        v1_report=V1, data_provider="synthetic_pending_cost",
    )[0]
    report, ledger, _ = run_cost_scenario(
        synthetic_b1, prices, POLICY, b1_output_set_hash="synthetic-b1-output-set",
    )
    pending_rows = [row for row in ledger["rows"] if row["pending_adjustment_id"]]
    assert pending_rows
    assert {row["execution_date"] for row in pending_rows} == {"2021-03-02"}
    assert report["cost_attribution"]["completed_pending_cost"] == round(
        sum(row["total_cost"] for row in pending_rows), 10
    )
    march_first = next(row for row in report["daily_portfolio_states"] if row["date"] == "2021-03-01")
    assert march_first["transaction_cost"] == 0


def test_pending_recovery_and_new_signal_use_sequential_event_nav():
    prices = deepcopy(PRICES)
    prices["510300.SH"] = [row for row in prices["510300.SH"] if row.date != "2021-03-01"]
    research = {
        "period": {"start": "2021-02-18", "end": "2021-03-05"},
        "monthly_allocations": [
            {"date": "2021-02-19", "weights": {"H00300.CSI": 0.25, "CASH": 0.75}},
            {"date": "2021-02-26", "weights": {"CASH": 1.0}},
            {"date": "2021-03-01", "weights": {"H00300.CSI": 0.1, "CASH": 0.9}},
        ],
    }
    synthetic_b1 = run_execution_backtest_v2(
        research, prices, MAPPINGS, ASSETS, CALENDAR, METADATA,
        v1_report=V1, data_provider="synthetic_same_day_events",
    )[0]
    report, ledger, comparison = run_cost_scenario(
        synthetic_b1, prices, POLICY, b1_output_set_hash="synthetic-same-day-output-set",
    )
    rows = [row for row in ledger["rows"] if row["execution_date"] == "2021-03-02"]
    assert [row["direction"] for row in rows] == ["sell", "buy"]
    assert rows[0]["pending_adjustment_id"] is not None
    assert rows[1]["pending_adjustment_id"] is None
    assert rows[1]["event_pre_trade_nav"] == rows[0]["event_post_trade_nav"]
    assert rows[1]["requested_post_trade_value"] == pytest.approx(
        rows[1]["event_pre_trade_nav"] * 0.1, abs=VALUE_TOLERANCE
    )
    assert rows[0]["post_trade_cash"] == rows[1]["pre_trade_cash"]
    assert rows[0]["post_trade_cash"] != rows[1]["post_trade_cash"]
    daily = next(row for row in report["daily_portfolio_states"] if row["date"] == "2021-03-02")
    assert rows[-1]["post_trade_cash"] == daily["closing_cash"]
    cost_validation.cross_validate_cost_outputs({
        cost_validation.REPORT.name: report,
        cost_validation.LEDGER.name: ledger,
        cost_validation.COMPARISON.name: comparison,
    })


def test_superseded_pending_is_not_charged_and_replacement_is_charged_once():
    prices = deepcopy(PRICES)
    missing = {"2021-03-01", "2021-03-02"}
    prices["510300.SH"] = [row for row in prices["510300.SH"] if row.date not in missing]
    research = {
        "period": {"start": "2021-02-18", "end": "2021-03-05"},
        "monthly_allocations": [
            {"date": "2021-02-19", "weights": {"H00300.CSI": 0.25, "CASH": 0.75}},
            {"date": "2021-02-26", "weights": {"CASH": 1.0}},
            {"date": "2021-03-01", "weights": {"H00300.CSI": 0.1, "CASH": 0.9}},
        ],
    }
    synthetic_b1 = run_execution_backtest_v2(
        research, prices, MAPPINGS, ASSETS, CALENDAR, METADATA,
        v1_report=V1, data_provider="synthetic_superseded_cost",
    )[0]
    superseded, replacement = synthetic_b1["pending_adjustments"]
    assert superseded["status"] == "superseded"
    assert replacement["status"] == "completed"
    _, ledger, _ = run_cost_scenario(
        synthetic_b1, prices, POLICY, b1_output_set_hash="synthetic-superseded-output-set",
    )
    pending_ids = [row["pending_adjustment_id"] for row in ledger["rows"] if row["pending_adjustment_id"]]
    assert superseded["adjustment_id"] not in pending_ids
    assert pending_ids.count(replacement["adjustment_id"]) == 1
    assert {row["execution_date"] for row in ledger["rows"] if row["pending_adjustment_id"]} == {"2021-03-03"}


@pytest.mark.parametrize("relative", [
    "data/execution_prices/510300_SH.json",
    "reports/research_backtest_report.json",
    "reports/execution_backtest_v2_report.json",
    "reports/execution_investability_timeline.json",
])
def test_current_b1_source_or_artifact_drift_makes_b2_unavailable(relative):
    target = cost_validation.ROOT / relative
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n")
        result = cost_validation.verify_cost_output_set()
        assert result["verified"] is False
        assert any("B1 dependency invalid" in error for error in result["errors"])
    finally:
        target.write_bytes(original)
    assert cost_validation.verify_cost_output_set()["verified"] is True


def test_current_policy_drift_makes_old_b2_unavailable():
    original = POLICY_PATH.read_bytes()
    try:
        raw = json.loads(original)
        raw["commission"]["buy_bps"] += 1
        POLICY_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        result = cost_validation.verify_cost_output_set()
        assert result["verified"] is False
        assert any("current sources" in error or "policy" in error for error in result["errors"])
    finally:
        POLICY_PATH.write_bytes(original)
    assert cost_validation.verify_cost_output_set()["verified"] is True


def test_b1_marker_output_set_drift_makes_b2_unavailable():
    original = B1_COMMITTED.read_bytes()
    try:
        marker = json.loads(original)
        marker["output_set_hash"] = "stale-b1-output-set"
        B1_COMMITTED.write_text(json.dumps(marker), encoding="utf-8")
        assert cost_validation.verify_cost_output_set()["verified"] is False
    finally:
        B1_COMMITTED.write_bytes(original)


@pytest.mark.parametrize("component", [
    "cost_policy_hash",
    "b1_output_set_hash",
    "master_date_grid_hash",
    "engine_code_hash",
    "engine_source_hashes",
])
def test_rehashed_artifacts_with_stale_run_components_fail_identity(component):
    targets = (*cost_validation.ARTIFACTS, cost_validation.MANIFEST, cost_validation.COMMITTED)
    originals = {path: path.read_bytes() for path in targets}
    report = deepcopy(REPORT)
    ledger = deepcopy(LEDGER)
    comparison = deepcopy(COMPARISON)
    if component == "engine_source_hashes":
        key = next(iter(report["run_identity_components"][component]))
        report["run_identity_components"][component][key] = "stale-engine-source"
    else:
        report["run_identity_components"][component] = f"stale-{component}"
    try:
        cost_validation.write_cost_outputs(report, ledger, comparison)
        result = cost_validation.verify_cost_output_set()
        assert result["verified"] is False
        assert any("run identity components" in error for error in result["errors"])
    finally:
        for path, content in originals.items():
            path.write_bytes(content)


def test_manifest_and_marker_identity_fields_are_enforced():
    targets = (cost_validation.MANIFEST, cost_validation.COMMITTED)
    originals = {path: path.read_bytes() for path in targets}
    try:
        manifest = json.loads(originals[cost_validation.MANIFEST])
        manifest["output_set_hash"] = "not-reproducible"
        manifest["policy_sha256"] = "stale-policy"
        cost_validation.MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
        marker = json.loads(originals[cost_validation.COMMITTED])
        marker["run_id"] = "stale-run"
        cost_validation.COMMITTED.write_text(json.dumps(marker), encoding="utf-8")
        result = cost_validation.verify_cost_output_set()
        assert result["verified"] is False
        assert any("output-set hash cannot be reproduced" in error for error in result["errors"])
        assert any("marker and manifest run IDs" in error for error in result["errors"])
        assert any("manifest policy_sha256" in error for error in result["errors"])
    finally:
        for path, content in originals.items():
            path.write_bytes(content)


def test_b1_output_set_and_business_hash_remain_unchanged():
    assert json.loads(B1_COMMITTED.read_text(encoding="utf-8"))["output_set_hash"] == B1_OUTPUT_SET_HASH
    assert B1["b1_golden_freeze"]["actual_semantic_sha256"] == "612062e915811ce6588ba276f339d819d9fe3e164127247546e262f7984e2e55"


@pytest.mark.parametrize("target", cost_validation.ARTIFACTS)
def test_cost_output_tamper_fails_closed(target):
    original = target.read_bytes()
    try:
        value = json.loads(original)
        value["tampered"] = True
        _atomic_test_write(target, json.dumps(value).encode("utf-8"))
        assert cost_validation.load_cost_report()["available"] is False
    finally:
        _atomic_test_write(target, original)


def test_cost_marker_missing_fails_closed():
    original = cost_validation.COMMITTED.read_bytes()
    cost_validation.COMMITTED.unlink()
    try:
        assert cost_validation.load_cost_report()["available"] is False
    finally:
        cost_validation.COMMITTED.write_bytes(original)


def test_cost_output_set_is_verified_and_cross_file_consistent():
    assert cost_validation.verify_cost_output_set()["verified"] is True
    assert REPORT["run_id"] == LEDGER["run_id"] == COMPARISON["run_id"]
    assert REPORT["policy_sha256"] == LEDGER["policy_sha256"] == COMPARISON["policy_sha256"]


def test_cost_report_contains_no_trading_instruction_fields():
    text = json.dumps(REPORT).lower()
    for forbidden in ('"order"', '"quantity"', '"shares"', '"target_price"'):
        assert forbidden not in text
