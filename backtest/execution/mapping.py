def build_execution_mapping(research_allocations, asset_mappings, execution_universe, *, allow_low_quality_proxy=False):
    execution_ids={asset.asset_id for asset in execution_universe}; by_research={row.research_asset_id:row for row in asset_mappings}; used={asset_id for allocation in research_allocations for asset_id in allocation.get('weights',{}) if asset_id!='CASH'}; rows=[]
    for asset_id in sorted(used):
        mapping=by_research.get(asset_id); quality=mapping.mapping_quality if mapping else "none"; proxy=mapping.primary_execution_proxy if mapping else None; approval=mapping.execution_approval if mapping else "research_only"
        allowed=bool(proxy and proxy in execution_ids and approval != "research_only" and (quality in {"high","medium"} or approval == "human_approved" or (allow_low_quality_proxy and quality=="low")))
        reason="mapped" if allowed else ("low_quality_proxy_excluded" if quality=="low" else "mapping_unavailable")
        rows.append({"research_asset_id":asset_id,"proxy_id":proxy if allowed else None,"mapping_quality":quality,"execution_approval":approval,"executable":allowed,"reason":reason})
    return rows
