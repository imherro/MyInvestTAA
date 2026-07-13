def validate_mapping_review(provenance, proposal, impact, collision_violation, semantic_quality):
    reasons=[]
    if not provenance.get("provenance_verified"):reasons.append("dataset provenance not verified")
    if not proposal.get("eligible_for_recommendation"):reasons.append("candidate is not eligible")
    if semantic_quality not in {"strong","acceptable"}:reasons.append("semantic quality is not approvable")
    if impact.get("tradable_weight_coverage_delta",0)<=0:reasons.append("tradable coverage did not improve")
    if impact.get("annual_return_delta",0)<-.02:reasons.append("annual return declined more than 2%")
    if impact.get("max_drawdown_delta",0)<-.05:reasons.append("max drawdown worsened more than 5%")
    if collision_violation:reasons.append("single ETF aggregate weight exceeds 35%")
    if not proposal.get("requires_manual_approval"):reasons.append("manual approval flag missing")
    return {"result":"recommend_manual_approval" if not reasons else ("reject_proxy" if semantic_quality=="invalid" else "retain_research_only"),"reasons":reasons,"requires_manual_approval":True}
