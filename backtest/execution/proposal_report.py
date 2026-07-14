import json
import hashlib
from engine.asset_registry.loader import ROOT
from engine.asset_registry.loader import ASSET_MAPPING_FILE

PROPOSAL=ROOT/"reports"/"execution_mapping_proposal.json"; COUNTER=ROOT/"reports"/"execution_mapping_counterfactual_report.json"
COUNTERFACTUAL_BASELINE_SOURCES={
    "asset_mapping":ASSET_MAPPING_FILE,
    "decision_ledger":ROOT/"data"/"universe"/"execution_mapping_decision_ledger.json",
    "approval_integrity_seal":ROOT/"reports"/"execution_mapping_approval_integrity_seal.json",
    "execution_backtest_report":ROOT/"reports"/"execution_backtest_report.json",
}
def write_report(report,path): path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return path
def load_report(path,message):
    if not path.exists():return {"available":False,"message":message}
    value=json.loads(path.read_text(encoding="utf-8"));value["available"]=True;return value
def load_mapping_proposal_report():return load_report(PROPOSAL,"execution mapping proposal report not generated yet")
def build_counterfactual_baseline_contract():
    sources={name:{"path":str(path.relative_to(ROOT)).replace("\\","/"),"sha256":_sha256(path)} for name,path in COUNTERFACTUAL_BASELINE_SOURCES.items()}
    execution_report=json.loads(COUNTERFACTUAL_BASELINE_SOURCES["execution_backtest_report"].read_text(encoding="utf-8"))
    baseline_snapshot=_baseline_snapshot(execution_report)
    contract={"schema_version":"1.0","sources":sources,"baseline_snapshot":baseline_snapshot,"baseline_snapshot_hash":_semantic_hash(baseline_snapshot)}
    contract["contract_hash"]=_semantic_hash(contract)
    return contract
def validate_counterfactual_baseline_contract(contract,baseline):
    expected=build_counterfactual_baseline_contract();errors=[]
    if not isinstance(contract,dict): errors.append("counterfactual baseline contract is missing")
    else:
        if contract.get("schema_version")!="1.0": errors.append("counterfactual baseline contract schema is unsupported")
        for name,current in expected["sources"].items():
            recorded=contract.get("sources",{}).get(name,{})
            if recorded.get("path")!=current["path"]: errors.append(f"counterfactual baseline source path mismatch: {name}")
            if recorded.get("sha256")!=current["sha256"]: errors.append(f"counterfactual baseline source hash mismatch: {name}")
        if contract.get("baseline_snapshot")!=expected["baseline_snapshot"]: errors.append("counterfactual baseline snapshot no longer matches current execution report")
        if contract.get("baseline_snapshot_hash")!=expected["baseline_snapshot_hash"]: errors.append("counterfactual baseline snapshot hash mismatch")
        if _baseline_snapshot(baseline)!=expected["baseline_snapshot"]: errors.append("counterfactual embedded baseline does not match current execution report")
        if contract.get("contract_hash")!=expected["contract_hash"]: errors.append("counterfactual baseline contract hash mismatch")
    return {"verified":not errors,"status":"current" if not errors else "stale","evidence_use":"current_analysis" if not errors else "historical_only","errors":errors,"current_contract":expected}
def load_counterfactual_report(path=None):
    value=load_report(path or COUNTER,"execution mapping counterfactual report not generated yet")
    if not value.get("available"): return value
    status=validate_counterfactual_baseline_contract(value.get("baseline_contract"),value.get("baseline",{}))
    value["baseline_contract_verification"]=status
    value["status"]=status["status"]
    value["evidence_use"]=status["evidence_use"]
    if not status["verified"]:
        value.setdefault("decision",{})["ready_for_manual_mapping_approval"]=False
        value["decision"]["reasons"]=list(dict.fromkeys([*value["decision"].get("reasons",[]),"counterfactual baseline no longer matches current formal sources"]))
        value.setdefault("warnings",[]).append("Historical-only counterfactual: baseline sources do not match the current formal configuration.")
    return value
def _sha256(path):
    if not path.exists(): return None
    return hashlib.sha256(path.read_bytes()).hexdigest()
def _semantic_hash(value):
    payload=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
def _baseline_snapshot(report):
    summary=report.get("mapping_summary",{})
    return {
        "strategy":report.get("strategy"),
        "data_provider":report.get("data_provider"),
        "period":report.get("period"),
        "metrics":report.get("metrics"),
        "mapping_summary":{key:summary.get(key) for key in (
            "mapped_research_assets","unmapped_research_assets","low_quality_proxy_assets",
            "untradable_months","untradable_month_ratio","binary_any_gap_month_ratio",
            "mapping_weight_coverage","tradable_weight_coverage",
            "tradable_weight_coverage_total_portfolio","coverage_contract","gap_metrics",
            "mapping_count_scope",
        )},
        "aggregate_cash_breakdown":report.get("aggregate_cash_breakdown"),
    }
