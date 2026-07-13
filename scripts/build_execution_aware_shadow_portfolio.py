from __future__ import annotations

import json
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
from backtest.execution.shadow_portfolio import (
    build_execution_aware_shadow_portfolio,
)
from backtest.execution.shadow_report import (
    write_execution_aware_shadow_portfolio,
)
from backtest.research.report import load_research_backtest_report
from engine.asset_registry import load_asset_mappings, load_execution_universe

assets = load_execution_universe()
manifest = load_price_dataset_manifest()
provenance = {**manifest, **verify_price_dataset_manifest(manifest, assets)}
report = build_execution_aware_shadow_portfolio(
    load_research_backtest_report(),
    load_asset_mappings(),
    load_execution_price_dataset(assets),
    provenance,
    load_mapping_decision_ledger(),
    load_mapping_approval_record(),
)
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
