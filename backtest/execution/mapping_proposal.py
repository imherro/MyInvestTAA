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


def proposal_collisions(proposals, allocations, baseline_mappings=None):
    overlay={row["research_asset_id"]:row["proposed_primary_execution_proxy"] for row in proposals}
    used={asset for allocation in allocations for asset in allocation.get("weights",{}) if asset!="CASH"}
    by_research={mapping.research_asset_id:overlay.get(mapping.research_asset_id,mapping.primary_execution_proxy) for mapping in (baseline_mappings or []) if mapping.research_asset_id in used}
    by_research.update(overlay)
    collisions=[]
    for proxy in sorted(set(by_research.values())-{None}):
        assets=sorted(asset for asset,value in by_research.items() if value==proxy);weights=[sum(float(a.get("weights",{}).get(asset,0)) for asset in assets) for a in allocations]
        maximum=max(weights,default=0.0);average=sum(weights)/len(weights) if weights else 0.0
        if len(assets)>1 or maximum>.35: collisions.append({"proxy_id":proxy,"research_asset_ids":assets,"max_aggregate_weight":round(maximum,6),"average_aggregate_weight":round(average,6),"months_above_30_percent":sum(value>.30 for value in weights),"months_above_35_percent":sum(value>.35 for value in weights),"violation":"aggregate_weight_above_35pct" if maximum>.35 else None})
    return {"proxy_collisions":collisions,"has_weight_violation":any(row["violation"] for row in collisions)}
