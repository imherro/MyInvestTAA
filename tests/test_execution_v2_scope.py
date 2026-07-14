from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields
import hashlib
import json
from pathlib import Path

import pytest

from backtest.execution.v2.contracts import (
    ExecutionCoreConfig,
    ExecutionCoreInputs,
    ExecutionCoreResult,
    ExecutionVersionStatus,
    SourceManifestEntry,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "backtest" / "execution" / "v2" / "contracts.py"
B1_GOLDEN_HASH = "612062e915811ce6588ba276f339d819d9fe3e164127247546e262f7984e2e55"
B1_OUTPUT_SET_HASH = "3edefb9ede72dd40bcb5416be593699306859f5f5898dce7b7778df800174615"
B2_OUTPUT_SET_HASH = "f7be8bb0358b627fab431d105f806023955d4435292245dcf7fe4ab99ea99252"
V1_REPORT_SHA256 = "3e99e333c70ff12ed43914ddb8ae17a27c85dca6e7fa8eaf2744f31a872b952d"
RELEASE_ID = "taa-20260713-a6fb68fb8630"


def _read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _sha256(relative):
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def test_c0a_contracts_are_frozen_and_not_publicly_exported():
    instances = (
        SourceManifestEntry("prices", "data/prices.json", "a" * 64, "market_data"),
        ExecutionCoreConfig(),
        ExecutionVersionStatus(
            version="V2_B1",
            lifecycle_status="core_candidate",
            semantics="zero_cost_core_semantics",
            production_actionable=False,
            current_formal_gate_source=False,
            current_decision_member=False,
            release_gate_member=False,
            maintenance_mode="core_stabilization",
        ),
    )
    for instance in instances:
        assert instance.__class__.__dataclass_params__.frozen is True
        with pytest.raises(FrozenInstanceError):
            setattr(instance, fields(instance)[0].name, "changed")

    package_source = (ROOT / "backtest/execution/v2/__init__.py").read_text(encoding="utf-8")
    assert "ExecutionCore" not in package_source
    assert "SourceManifestEntry" not in package_source


def test_core_contract_contains_required_inputs_and_results():
    input_names = {field.name for field in fields(ExecutionCoreInputs)}
    assert {
        "research_report",
        "execution_price_data",
        "approved_mappings",
        "execution_universe",
        "trade_calendar",
        "instrument_metadata",
        "source_manifest",
        "config",
    } == input_names

    result_names = {field.name for field in fields(ExecutionCoreResult)}
    assert {
        "core_run_id",
        "periods",
        "equity_curve",
        "daily_states",
        "signal_events",
        "pending_adjustments",
        "investability_timeline",
        "coverage_contract",
        "gap_metrics",
        "source_manifest",
        "validation",
    } == result_names
    assert "comparison" not in " ".join(result_names).lower()


def test_core_config_has_no_non_core_extension_points():
    names = {field.name for field in fields(ExecutionCoreConfig)}
    assert names == {"strategy_id", "engine_status", "schema_version"}
    forbidden = {
        "commission",
        "slippage",
        "tax",
        "cash_yield",
        "liquidity",
        "market_impact",
    }
    assert names.isdisjoint(forbidden)


def test_contract_module_has_no_filesystem_fastapi_or_b2_dependency():
    source = CONTRACTS.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
    lowered = " ".join(imports).lower()
    assert "fastapi" not in lowered
    assert "cost_domain" not in lowered
    assert "backtest.execution.v2.costs" not in lowered
    assert "backtest.execution.v2.scenario" not in lowered
    assert "pathlib" not in lowered
    assert "os" not in imports
    assert "open" not in calls
    assert "read_text" not in calls
    assert "read_bytes" not in calls
    assert "ROOT" not in source


def test_c0a_frozen_execution_hashes_are_unchanged():
    assert _sha256("reports/execution_backtest_report.json") == V1_REPORT_SHA256
    b1 = _read_json("reports/execution_backtest_v2_report.json")
    assert b1["b1_golden_freeze"]["actual_semantic_sha256"] == B1_GOLDEN_HASH
    assert _read_json("reports/execution_v2_COMMITTED.json")["output_set_hash"] == B1_OUTPUT_SET_HASH
    assert _read_json("reports/execution_v2_b2_cost_COMMITTED.json")["output_set_hash"] == B2_OUTPUT_SET_HASH
    assert _read_json("reports/release/current/COMMITTED.json")["release_id"] == RELEASE_ID


def test_formal_release_and_current_decision_still_use_v1_execution():
    decision = _read_json("reports/release/current/current_market_decision.json")
    assert decision["execution_validation"]["source"] == "reports/execution_backtest_report.json"
    manifest_text = (ROOT / "reports/release/current/release_manifest.json").read_text(encoding="utf-8")
    assert "execution_backtest_report.json" in manifest_text
    assert "execution_backtest_v2_b2_cost_report.json" not in manifest_text
    assert "execution_v2_b2" not in json.dumps(decision).lower()


def test_lifecycle_and_non_goal_documents_freeze_scope():
    lifecycle = (ROOT / "docs/EXECUTION_VERSION_LIFECYCLE.md").read_text(encoding="utf-8")
    non_goals = (ROOT / "docs/NON_GOALS.md").read_text(encoding="utf-8")
    frozen = (ROOT / "docs/experiments/EXECUTION_COST_B2_FROZEN.md").read_text(encoding="utf-8")
    completion = (ROOT / "docs/CORE_COMPLETION_CRITERIA.md").read_text(encoding="utf-8")

    assert "formal_legacy_execution_baseline" in lifecycle
    assert "current_formal_gate_source" in lifecycle
    assert "core_candidate" in lifecycle
    assert "zero_cost_core_semantics" in lifecycle
    assert "frozen_archived_research_experiment" in lifecycle
    assert B2_OUTPUT_SET_HASH in frozen
    assert B1_OUTPUT_SET_HASH in lifecycle
    assert B1_GOLDEN_HASH in completion
    for task in ("B2-1-Fix2", "B2-2", "B2-3"):
        assert task in non_goals
    assert "已取消" in non_goals
    assert "不再进入开发计划" in non_goals


def test_scope_documents_define_identity_split_and_non_trading_boundary():
    scope = (ROOT / "docs/PROJECT_SCOPE.md").read_text(encoding="utf-8")
    execution = (ROOT / "docs/EXECUTION_V2.md").read_text(encoding="utf-8")
    lifecycle = (ROOT / "docs/EXECUTION_VERSION_LIFECYCLE.md").read_text(encoding="utf-8")
    combined = "\n".join((scope, execution, lifecycle))
    assert "core_run_id" in combined
    assert "artifact_run_id" in combined
    assert "不绑定 V1" in combined
    assert "不输出订单、股数、金额、目标价格" in combined
    assert "transaction cost = 0" in execution
    assert "cash yield = 0" in execution
