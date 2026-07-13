from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backtest.execution.approval_integrity import (
    APPROVAL_INTEGRITY_SEAL,
    load_approval_integrity_seal,
)
from backtest.execution.approval_package import DECISION_LEDGER
from backtest.execution.dataset_provenance import (
    PRICE_MANIFEST_REPORT,
    load_price_dataset_manifest,
    verify_price_dataset_manifest,
)
from backtest.execution.report import EXECUTION_BACKTEST_REPORT, load_execution_backtest_report
from backtest.execution.shadow_report import (
    SHADOW_PORTFOLIO_REPORT,
    load_execution_aware_shadow_portfolio,
)
from backtest.research.report import RESEARCH_BACKTEST_REPORT, load_research_backtest_report
from decision.current_market.models import SourceSnapshot
from engine.asset_registry import load_execution_universe
from engine.asset_registry.loader import ASSET_MAPPING_FILE, ROOT


STRATEGY_DIAGNOSIS_REPORT = ROOT / "reports" / "strategy_diagnosis_report.json"
EXECUTION_GATE_POLICY = ROOT / "config" / "execution_validation_policy.json"
V11_CURRENT_ALLOCATION_REPORT = ROOT / "reports" / "v11_current_allocation.json"


SOURCE_DEFINITIONS = {
    "market_and_v11": (STRATEGY_DIAGNOSIS_REPORT, True, "market_data"),
    "research_allocation": (RESEARCH_BACKTEST_REPORT, True, "market_data"),
    "execution_validation": (EXECUTION_BACKTEST_REPORT, True, "market_data"),
    "execution_shadow": (SHADOW_PORTFOLIO_REPORT, True, "market_data"),
    "execution_price_manifest": (PRICE_MANIFEST_REPORT, True, "market_data"),
    "approval_integrity": (APPROVAL_INTEGRITY_SEAL, True, "governance"),
    "decision_ledger": (DECISION_LEDGER, True, "governance"),
    "asset_mapping": (ASSET_MAPPING_FILE, True, "governance"),
    "execution_gate_policy": (EXECUTION_GATE_POLICY, True, "policy"),
    "v11_current_allocation": (V11_CURRENT_ALLOCATION_REPORT, False, "market_data"),
}


def load_current_market_sources() -> dict:
    diagnosis = _load_json_report(
        STRATEGY_DIAGNOSIS_REPORT, "strategy diagnosis report not found"
    )
    research = load_research_backtest_report()
    execution = load_execution_backtest_report()
    shadow = load_execution_aware_shadow_portfolio()
    price_manifest = load_price_dataset_manifest()
    integrity = load_approval_integrity_seal()
    ledger = _load_json_report(DECISION_LEDGER, "mapping decision ledger not found")
    mappings = _load_json_report(ASSET_MAPPING_FILE, "asset mapping registry not found")
    gate_policy = _load_json_report(
        EXECUTION_GATE_POLICY, "execution validation policy not found"
    )
    v11_allocation = _load_json_report(
        V11_CURRENT_ALLOCATION_REPORT, "current V11 allocation snapshot not found"
    )
    price_verification = (
        verify_price_dataset_manifest(price_manifest, load_execution_universe())
        if price_manifest.get("available")
        else {"provenance_verified": False, "errors": ["price manifest unavailable"]}
    )
    as_of = {
        "market_and_v11": diagnosis.get("dataset", {}).get("period", {}).get("end"),
        "research_allocation": research.get("period", {}).get("end"),
        "execution_validation": execution.get("period", {}).get("end"),
        "execution_shadow": shadow.get("data_as_of"),
        "execution_price_manifest": price_manifest.get("end"),
        "approval_integrity": integrity.get("decision_date"),
        "decision_ledger": _approved_at(ledger),
        "asset_mapping": integrity.get("decision_date"),
        "execution_gate_policy": None,
        "v11_current_allocation": v11_allocation.get("as_of"),
    }
    source_manifest = {
        name: SourceSnapshot(
            source=name,
            path=_relative(path),
            sha256=_sha256(path) if path.exists() else None,
            available=path.exists(),
            source_as_of=as_of.get(name),
            required=required,
            temporal_role=temporal_role,
        ).as_dict()
        for name, (path, required, temporal_role) in SOURCE_DEFINITIONS.items()
    }
    return {
        "diagnosis": diagnosis,
        "research": research,
        "execution": execution,
        "shadow": shadow,
        "price_manifest": price_manifest,
        "price_verification": price_verification,
        "approval_integrity": integrity,
        "decision_ledger": ledger,
        "asset_mapping": mappings,
        "gate_policy": gate_policy,
        "v11_allocation": v11_allocation,
        "source_manifest": source_manifest,
    }


def _load_json_report(path: Path, message: str):
    if not path.exists():
        return {"available": False, "message": message}
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value["available"] = True
    return value


def _approved_at(ledger: dict) -> str | None:
    return next(
        (
            row.get("approved_at")
            for row in ledger.get("decisions", [])
            if row.get("status") == "approved_for_execution_validation"
        ),
        None,
    )


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
