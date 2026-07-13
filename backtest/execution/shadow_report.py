from __future__ import annotations

import json
import hashlib
from pathlib import Path

from engine.asset_registry.loader import ROOT
from backtest.execution.approval_transaction import transaction_is_pending

SHADOW_PORTFOLIO_REPORT = ROOT / "reports" / "execution_aware_shadow_portfolio.json"


def write_execution_aware_shadow_portfolio(report, path: Path | None = None):
    target = path or SHADOW_PORTFOLIO_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def load_execution_aware_shadow_portfolio(path: Path | None = None):
    if transaction_is_pending():
        return {"available": False, "message": "approval transaction is pending"}
    target = path or SHADOW_PORTFOLIO_REPORT
    if not target.exists():
        return {
            "available": False,
            "message": "execution-aware shadow portfolio not generated yet",
        }
    report = json.loads(target.read_text(encoding="utf-8"))
    if target.resolve() == SHADOW_PORTFOLIO_REPORT.resolve():
        errors = _snapshot_errors(report.get("snapshot_integrity", {}))
        if errors:
            return {
                "available": False,
                "message": "shadow snapshot integrity verification failed",
                "errors": errors,
            }
    report["available"] = True
    return report


def _snapshot_errors(snapshot):
    from backtest.execution.approval_integrity import (
        APPROVAL_INTEGRITY_SEAL,
        APPROVAL_RECORD,
    )
    from backtest.execution.approval_package import DECISION_LEDGER
    from backtest.execution.dataset_provenance import PRICE_MANIFEST_REPORT
    from backtest.research.report import RESEARCH_BACKTEST_REPORT
    from engine.asset_registry.loader import ASSET_MAPPING_FILE

    paths = {
        "research_report_hash": RESEARCH_BACKTEST_REPORT,
        "mapping_registry_hash": ASSET_MAPPING_FILE,
        "decision_ledger_hash": DECISION_LEDGER,
        "approval_record_hash": APPROVAL_RECORD,
        "approval_seal_hash": APPROVAL_INTEGRITY_SEAL,
        "price_manifest_hash": PRICE_MANIFEST_REPORT,
    }
    errors = []
    for field, source in paths.items():
        if not source.exists():
            errors.append(f"snapshot source missing: {source.name}")
            continue
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if snapshot.get(field) != actual:
            errors.append(f"snapshot hash mismatch: {field}")
    if snapshot.get("verified") is not True:
        errors.append("snapshot was not marked verified")
    return errors
