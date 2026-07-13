from __future__ import annotations

import json
from pathlib import Path

from backtest.execution.counterfactual import run_mapping_counterfactual
from backtest.execution.drawdown_attribution import drawdown_window
from backtest.execution.mapping_proposal import proposal_collisions
from backtest.execution.proposal_attribution import build_exact_drawdown_attribution
from engine.asset_registry.loader import ROOT

TARGET_ASSET_ID = "931743CNY010.CSI"
TARGET_PROXY_ID = "512760.SH"
SEMANTIC_EVIDENCE = ROOT / "reports" / "execution_mapping_931743_semantic_evidence.json"
APPROVAL_PACKAGE = ROOT / "reports" / "execution_mapping_931743_approval_package.json"
DECISION_LEDGER = ROOT / "data" / "universe" / "execution_mapping_decision_ledger.json"


def build_selective_approval_package(
    research,
    mappings,
    proposal,
    prices,
    assets,
    provenance,
    semantic_evidence,
    *,
    data_provider,
    formal_mapping_unchanged,
):
    baseline, selective, common, impact = run_mapping_counterfactual(
        research,
        mappings,
        [proposal],
        prices,
        assets,
        data_provider=data_provider,
    )
    baseline_window = drawdown_window(baseline)
    selective_window = drawdown_window(selective)
    baseline_exact = build_exact_drawdown_attribution(
        baseline, prices, baseline_window
    )
    selective_exact = build_exact_drawdown_attribution(
        selective, prices, selective_window
    )
    collisions = proposal_collisions(
        [proposal], research.get("monthly_allocations", []), mappings
    )
    target_collision = next(
        (
            row
            for row in collisions["proxy_collisions"]
            if row["proxy_id"] == TARGET_PROXY_ID
        ),
        None,
    )
    readiness_reasons = _readiness_reasons(
        provenance,
        proposal,
        semantic_evidence,
        impact,
        target_collision,
        selective_exact,
        formal_mapping_unchanged,
    )
    return {
        "available": True,
        "research_asset_id": TARGET_ASSET_ID,
        "proposed_proxy": TARGET_PROXY_ID,
        "dataset_provenance": provenance,
        "candidate_statistical_evidence": {
            key: proposal.get(key)
            for key in (
                "candidate_score",
                "correlation",
                "tracking_error_annualized",
                "overlap_days",
                "eligible_for_recommendation",
            )
        },
        "semantic_evidence": semantic_evidence,
        "baseline_metrics": baseline.get("common_period_metrics", {}),
        "selective_counterfactual_metrics": selective.get(
            "common_period_metrics", {}
        ),
        "common_comparison_period": common,
        "exact_drawdown_attribution": {
            "baseline_window": baseline_window,
            "baseline_reconciliation": baseline_exact,
            "selective_window": selective_window,
            "selective_reconciliation": selective_exact,
        },
        "full_collision_exposure": target_collision,
        "marginal_deltas": impact,
        "limitations": semantic_evidence.get("limitations", []),
        "requires_manual_approval": True,
        "formal_mapping_unchanged": formal_mapping_unchanged,
        "ready_for_explicit_human_decision": not readiness_reasons,
        "readiness_reasons": readiness_reasons,
        "warning": "No formal mapping has been changed. Explicit human approval is required before updating asset_mapping.json.",
    }


def _readiness_reasons(
    provenance,
    proposal,
    semantic,
    impact,
    collision,
    exact,
    formal_mapping_unchanged,
):
    reasons = []
    if not provenance.get("provenance_verified"):
        reasons.append("dataset provenance is not verified")
    if exact.get("reconciliation_error", 1) > 0.000001:
        reasons.append("drawdown attribution does not reconcile")
    if not proposal.get("eligible_for_recommendation"):
        reasons.append("candidate is not statistically eligible")
    if semantic.get("semantic_quality") not in {"acceptable", "strong"}:
        reasons.append("semantic evidence is not acceptable")
    if impact.get("tradable_weight_coverage_delta", 0) <= 0:
        reasons.append("tradable coverage did not improve")
    if impact.get("annual_return_delta", 0) < -0.02:
        reasons.append("annual return declined more than 2%")
    if impact.get("max_drawdown_delta", 0) < -0.05:
        reasons.append("max drawdown worsened more than 5%")
    if collision and collision.get("max_aggregate_weight", 0) > 0.35:
        reasons.append("single ETF aggregate weight exceeds 35%")
    if not proposal.get("requires_manual_approval"):
        reasons.append("manual approval flag is missing")
    if not formal_mapping_unchanged:
        reasons.append("formal asset mapping has already changed")
    return reasons


def write_approval_package(value, path=None):
    target = path or APPROVAL_PACKAGE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def _load(path: Path, message: str):
    if not path.exists():
        return {"available": False, "message": message}
    value = json.loads(path.read_text(encoding="utf-8"))
    value["available"] = True
    return value


def load_mapping_approval_package(asset_id=TARGET_ASSET_ID, path=None):
    if asset_id != TARGET_ASSET_ID:
        return {"available": False, "message": "no approval package for asset"}
    return _load(path or APPROVAL_PACKAGE, "mapping approval package not generated yet")


def load_mapping_decision_ledger(path=None):
    value = _load(path or DECISION_LEDGER, "mapping decision ledger not found")
    if value.get("available") and isinstance(value.get("decisions"), list):
        value["frozen_count"] = sum(
            row.get("status") in {"research_only", "rejected_proxy"}
            for row in value["decisions"]
        )
    return value
