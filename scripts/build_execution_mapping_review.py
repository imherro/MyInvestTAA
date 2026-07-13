import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.execution.approval_package import load_mapping_decision_ledger
from backtest.execution.mapping_application import load_mapping_approval_record
from backtest.execution.mapping_proposal import proposal_collisions
from backtest.execution.proposal_report import PROPOSAL
from backtest.execution.review_report import ATTRIBUTION, REVIEW, write_review_report
from backtest.research.report import load_research_backtest_report
from engine.asset_registry import load_asset_mappings
from engine.asset_registry.loader import ASSET_MAPPING_FILE

proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
attribution = json.loads(ATTRIBUTION.read_text(encoding="utf-8"))
semantic = json.loads(
    (ROOT / "data/universe/execution_mapping_semantic_review.json").read_text(
        encoding="utf-8"
    )
)
ledger = load_mapping_decision_ledger()
approval_record = load_mapping_approval_record()
sem = {row["research_asset_id"]: row for row in semantic}
attr = {
    row["research_asset_id"]: row
    for row in attribution["proposal_attributions"]
}
decisions = {
    row["research_asset_id"]: row for row in ledger.get("decisions", [])
}
collisions = proposal_collisions(
    proposal["proposals"],
    load_research_backtest_report()["monthly_allocations"],
    load_asset_mappings(),
)
reviews = []
for row in proposal["proposals"]:
    frozen = decisions[row["research_asset_id"]]
    result = {
        "approved_for_execution_validation": "approved_for_execution_validation",
        "research_only": "retain_research_only",
        "rejected_proxy": "reject_proxy",
    }[frozen["status"]]
    reviews.append(
        {
            **row,
            "semantic_review": sem[row["research_asset_id"]],
            "marginal_attribution": attr[row["research_asset_id"]],
            "decision": {
                "result": result,
                "status": frozen["status"],
                "reasons": [frozen["decision_reason"]],
                "requires_manual_approval": True,
                "production_approved": False,
            },
        }
    )

approved = [
    asset_id
    for asset_id, row in decisions.items()
    if row["status"] == "approved_for_execution_validation"
]
retained = [
    asset_id for asset_id, row in decisions.items() if row["status"] == "research_only"
]
rejected = [
    asset_id for asset_id, row in decisions.items() if row["status"] == "rejected_proxy"
]
report = {
    "available": True,
    "dataset_provenance": attribution["dataset_provenance"],
    "proposal_reviews": reviews,
    "full_overlay_result": attribution["full_overlay"],
    "proxy_collision_diagnostics": collisions,
    "drawdown_attribution": attribution["full_overlay"],
    "mapping_registry_version": hashlib.sha256(ASSET_MAPPING_FILE.read_bytes()).hexdigest(),
    "approval_record": approval_record,
    "decision": {
        "approved_for_execution_validation": approved,
        "retain_research_only": retained,
        "rejected": rejected,
        "ready_for_mapping_update_task": False,
        "mapping_update_applied": bool(approved),
        "production_approved": False,
        "reasons": [
            "The single human-approved mapping is applied for execution validation and shadow use only."
        ],
    },
}
write_review_report(report, REVIEW)
print(report["decision"])
