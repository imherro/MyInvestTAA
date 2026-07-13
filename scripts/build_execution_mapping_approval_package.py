import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.execution.approval_package import (
    SEMANTIC_EVIDENCE,
    TARGET_ASSET_ID,
    build_selective_approval_package,
    write_approval_package,
)
from backtest.execution.data_loader import load_execution_price_dataset
from backtest.execution.dataset_provenance import (
    load_price_dataset_manifest,
    verify_price_dataset_manifest,
)
from backtest.execution.proposal_report import PROPOSAL
from backtest.research.report import load_research_backtest_report
from engine.asset_registry import load_asset_mappings, load_execution_universe

assets = load_execution_universe()
mappings = load_asset_mappings()
manifest = load_price_dataset_manifest()
provenance = {**manifest, **verify_price_dataset_manifest(manifest, assets)}
proposals = json.loads(PROPOSAL.read_text(encoding="utf-8"))["proposals"]
proposal = next(row for row in proposals if row["research_asset_id"] == TARGET_ASSET_ID)
semantic = json.loads(SEMANTIC_EVIDENCE.read_text(encoding="utf-8"))
formal_mapping_unchanged = next(
    row for row in mappings if row.research_asset_id == TARGET_ASSET_ID
).primary_execution_proxy is None
report = build_selective_approval_package(
    load_research_backtest_report(),
    mappings,
    proposal,
    load_execution_price_dataset(assets),
    assets,
    provenance,
    semantic,
    data_provider="tushare" if provenance["provenance_verified"] else "unverified_local",
    formal_mapping_unchanged=formal_mapping_unchanged,
)
write_approval_package(report)
print(
    {
        "research_asset_id": report["research_asset_id"],
        "ready_for_explicit_human_decision": report[
            "ready_for_explicit_human_decision"
        ],
        "reconciliation_error": report["exact_drawdown_attribution"][
            "selective_reconciliation"
        ]["reconciliation_error"],
    }
)
