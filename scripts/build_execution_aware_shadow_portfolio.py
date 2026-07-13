from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.execution.approval_package import load_mapping_decision_ledger
from backtest.execution.data_loader import load_execution_price_dataset
from backtest.execution.dataset_provenance import (
    load_price_dataset_manifest,
    verify_price_dataset_manifest,
)
from backtest.execution.mapping_application import load_mapping_approval_record
from backtest.execution.approval_integrity import (
    APPROVAL_INTEGRITY_SEAL,
    APPROVAL_RECORD,
    validate_approval_integrity,
)
from backtest.execution.approval_package import DECISION_LEDGER
from backtest.execution.approval_transaction import load_transaction_status
from backtest.execution.dataset_provenance import PRICE_MANIFEST_REPORT
from backtest.execution.shadow_portfolio import (
    build_execution_aware_shadow_portfolio,
)
from backtest.execution.shadow_report import (
    write_execution_aware_shadow_portfolio,
)
from backtest.research.report import RESEARCH_BACKTEST_REPORT, load_research_backtest_report
from engine.asset_registry import load_asset_mappings, load_execution_universe
from engine.asset_registry.loader import ASSET_MAPPING_FILE

assets = load_execution_universe()
manifest = load_price_dataset_manifest()
provenance = {**manifest, **verify_price_dataset_manifest(manifest, assets)}
approval_integrity = validate_approval_integrity()
snapshot_paths = {
    "research_report_hash": RESEARCH_BACKTEST_REPORT,
    "mapping_registry_hash": ASSET_MAPPING_FILE,
    "decision_ledger_hash": DECISION_LEDGER,
    "approval_record_hash": APPROVAL_RECORD,
    "approval_seal_hash": APPROVAL_INTEGRITY_SEAL,
    "price_manifest_hash": PRICE_MANIFEST_REPORT,
}
snapshot_errors = [
    f"snapshot file missing: {path.name}"
    for path in snapshot_paths.values()
    if not path.exists()
]
snapshot_integrity = {
    key: hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    for key, path in snapshot_paths.items()
}
snapshot_integrity["verified"] = not snapshot_errors and not load_transaction_status().get("pending")
snapshot_integrity["errors"] = snapshot_errors
report = build_execution_aware_shadow_portfolio(
    load_research_backtest_report(),
    load_asset_mappings(),
    load_execution_price_dataset(assets),
    provenance,
    load_mapping_decision_ledger(),
    load_mapping_approval_record(),
    approval_integrity,
    snapshot_integrity,
)
report["transaction_status"] = load_transaction_status()
write_execution_aware_shadow_portfolio(report)
print(
    json.dumps(
        {
            "available": report.get("available"),
            "status": report.get("status"),
            "source_allocation_date": report.get("source_allocation_date"),
            "data_as_of": report.get("data_as_of"),
            "execution_weights": report.get("execution_weights"),
            "production_approved": report.get("production_approved"),
        },
        ensure_ascii=False,
        indent=2,
    )
)
