from __future__ import annotations

from backtest.execution.proxy_scoring import score_proxy_candidate


def build_proxy_research_report(research_prices, execution_prices, mappings, blocked_asset_ids):
    mapping_by_id={mapping.research_asset_id:mapping for mapping in mappings}
    results=[]
    for research_id in blocked_asset_ids:
        mapping=mapping_by_id.get(research_id)
        candidates=[]
        for candidate_id, rows in execution_prices.items():
            scored=score_proxy_candidate(research_prices.get(research_id,[]),rows)
            candidates.append({"candidate_id":candidate_id,**scored,"warnings":["candidate research only; no automatic mapping update"]})
        candidates.sort(key=lambda item:item["score"],reverse=True)
        top=candidates[0] if candidates else None
        eligible=next((candidate for candidate in candidates if not candidate["hard_gate_reasons"]),None)
        action="keep_research_only"
        if eligible and eligible["recommended_mapping_quality"] in {"medium","high"}: action="propose_mapping_update"
        results.append({"research_asset_id":research_id,"current_mapping":{"primary_execution_proxy":mapping.primary_execution_proxy if mapping else None,"mapping_quality":mapping.mapping_quality if mapping else "none"},"candidate_rankings":candidates,"recommendation":{"action":action,"primary_execution_proxy":eligible["candidate_id"] if action=="propose_mapping_update" else None,"mapping_quality":eligible["recommended_mapping_quality"] if eligible else "none","requires_manual_approval":True}})
    return {"available":True,"research_assets":results,"warning":"Candidate results are research only. They do not modify asset_mapping.json or execution backtests."}
