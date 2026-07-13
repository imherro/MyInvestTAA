from __future__ import annotations


def build_mapping_proposal(proxy_report: dict) -> dict:
    proposals=[]
    for item in proxy_report.get("research_assets",[]):
        recommended=item.get("recommendation",{})
        candidate=next((x for x in item.get("candidate_rankings",[]) if x.get("candidate_id")==recommended.get("primary_execution_proxy")),None)
        if not candidate or not candidate.get("eligible_for_recommendation"): continue
        current=item.get("current_mapping",{})
        proposals.append({"research_asset_id":item["research_asset_id"],"current_primary_execution_proxy":current.get("primary_execution_proxy"),"proposed_primary_execution_proxy":candidate["candidate_id"],"current_mapping_quality":current.get("mapping_quality","none"),"proposed_mapping_quality":candidate["recommended_mapping_quality"],"candidate_score":candidate["score"],"correlation":candidate["correlation"],"tracking_error_annualized":candidate["tracking_error_annualized"],"overlap_days":candidate["overlap_days"],"eligible_for_recommendation":True,"requires_manual_approval":True})
    return {"available":True,"source_report":"execution_proxy_research_report.json","status":"pending_manual_approval","proposals":proposals,"warnings":["Proposal only. asset_mapping.json has not been modified."]}


def proposal_collisions(proposals, allocations):
    collisions=[]
    for proxy in sorted({row["proposed_primary_execution_proxy"] for row in proposals}):
        assets=[row["research_asset_id"] for row in proposals if row["proposed_primary_execution_proxy"]==proxy]
        aggregate=max((sum(float(a.get("weights",{}).get(asset,0)) for asset in assets) for a in allocations),default=0.0)
        if len(assets)>1 or aggregate>.35: collisions.append({"proxy_id":proxy,"research_asset_ids":assets,"max_aggregate_weight":round(aggregate,6),"violation":"aggregate_weight_above_35pct" if aggregate>.35 else None})
    return {"proxy_collisions":collisions,"has_weight_violation":any(row["violation"] for row in collisions)}
