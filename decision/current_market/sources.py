from __future__ import annotations

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
from decision.current_market.instrument_ids import (
    EXECUTION_INSTRUMENT_ALIASES,
    load_execution_instrument_aliases,
)
from decision.current_market.source_policy import ALL_SOURCE_DEFINITIONS, sha256_file
from decision.v11_current import load_v11_current_allocation
from engine.asset_registry import load_execution_universe
from engine.asset_registry.loader import ASSET_MAPPING_FILE, ROOT


STRATEGY_DIAGNOSIS_REPORT = ROOT / "reports" / "strategy_diagnosis_report.json"
EXECUTION_GATE_POLICY = ROOT / "config" / "execution_validation_policy.json"
V11_CURRENT_ALLOCATION_REPORT = ROOT / "reports" / "v11_current_allocation.json"


def load_current_market_sources(
    *,
    v11_allocation: dict | None = None,
    v11_source_path: Path | None = None,
) -> dict:
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
    if v11_allocation is None:
        v11_allocation = load_v11_current_allocation()
        v11_source_path = V11_CURRENT_ALLOCATION_REPORT
    instrument_aliases = load_execution_instrument_aliases(
        EXECUTION_INSTRUMENT_ALIASES
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
        "execution_instrument_aliases": None,
    }
    source_manifest = {
        name: SourceSnapshot(
            source=name,
            path=definition["path"],
            sha256=sha256_file(
                v11_source_path
                if name == "v11_current_allocation" and v11_source_path is not None
                else ROOT / definition["path"]
            )
            if (
                v11_source_path
                if name == "v11_current_allocation" and v11_source_path is not None
                else ROOT / definition["path"]
            ).exists()
            else None,
            available=(
                v11_source_path
                if name == "v11_current_allocation" and v11_source_path is not None
                else ROOT / definition["path"]
            ).exists(),
            source_as_of=as_of.get(name),
            required=definition["required"],
            temporal_role=definition["temporal_role"],
        ).as_dict()
        for name, definition in ALL_SOURCE_DEFINITIONS.items()
    }
    source_path_overrides = (
        {"v11_current_allocation": v11_source_path}
        if v11_source_path is not None
        and v11_source_path.resolve() != V11_CURRENT_ALLOCATION_REPORT.resolve()
        else {}
    )
    if source_path_overrides:
        source_manifest["v11_current_allocation"]["release_artifact_path"] = (
            "v11_current_allocation.json"
        )
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
        "instrument_aliases": instrument_aliases,
        "source_manifest": source_manifest,
        "source_path_overrides": source_path_overrides,
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
