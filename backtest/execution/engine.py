from backtest.execution.gap import build_execution_gap
from backtest.execution.mapping import build_execution_mapping
from backtest.execution.models import ExecutionBacktestConfig
from backtest.research.metrics import build_metrics

def run_execution_backtest(research_report, execution_price_data, mappings, execution_universe, *, config=None):
    cfg=config or ExecutionBacktestConfig(); allocations=research_report.get("monthly_allocations",[])
    if not research_report.get("available") or not allocations: return {"available":False,"message":"research backtest report is unavailable"}
    mapping_rows=build_execution_mapping(allocations,mappings,execution_universe,allow_low_quality_proxy=cfg.allow_low_quality_proxy); by_research={r["research_asset_id"]:r for r in mapping_rows}
    proxy_ids=sorted({r["proxy_id"] for r in mapping_rows if r["proxy_id"]})
    date_maps={proxy:{row.date:row.close for row in execution_price_data.get(proxy,[])} for proxy in proxy_ids}
    common=sorted(set.intersection(*(set(values) for values in date_maps.values()))) if date_maps else []
    research_start=research_report.get("period",{}).get("start")
    dates=[value for value in common if not research_start or value>=research_start]
    if len(dates)<2: return {"available":False,"message":"insufficient overlapping tradable ETF history","mapping_summary":_summary(mapping_rows,allocations)}
    translated=[]
    for allocation in allocations:
        weights={}; cash=float(allocation.get("weights",{}).get("CASH",0))
        for research_id,weight in allocation.get("weights",{}).items():
            if research_id=="CASH": continue
            row=by_research.get(research_id); proxy=row.get("proxy_id") if row else None
            if proxy and allocation["date"] in date_maps.get(proxy,{}): weights[proxy]=weights.get(proxy,0)+float(weight)
            else: cash+=float(weight)
        if cash>1e-10: weights["CASH"]=round(cash,10)
        translated.append({"date":allocation["date"],"weights":weights})
    curve=[{"date":dates[0],"value":1.0}]; current={"CASH":1.0}; allocation_index=0
    for index in range(1,len(dates)):
        while allocation_index<len(translated) and translated[allocation_index]["date"]<=dates[index-1]: current=translated[allocation_index]["weights"]; allocation_index+=1
        daily=sum(weight*(date_maps[proxy][dates[index]]/date_maps[proxy][dates[index-1]]-1) for proxy,weight in current.items() if proxy!="CASH" and date_maps[proxy][dates[index-1]]>0)
        curve.append({"date":dates[index],"value":round(curve[-1]["value"]*(1+daily),8)})
    research_curve=[row for row in research_report.get("equity_curve",[]) if row["date"]>=dates[0] and row["date"]<=dates[-1]]; research_overlap=_normalize(research_curve)
    execution_metrics=build_metrics(curve); research_metrics=build_metrics(research_overlap)
    summary=_summary(mapping_rows,allocations); gap=build_execution_gap(research_metrics,execution_metrics)
    report={"available":True,"strategy":cfg.strategy,"source_research_strategy":research_report.get("strategy"),"period":{"start":dates[0],"end":dates[-1]},"metrics":execution_metrics,"equity_curve":curve,"monthly_allocations":translated,"research_full_period_metrics":research_report.get("metrics",{}),"research_overlap_metrics":research_metrics,"execution_gap":{**gap,"cash_drag_gap":round(_cash_drag(translated)-_cash_drag(allocations),6)},"mapping_summary":summary,"unmapped_assets":[r for r in mapping_rows if not r["executable"]],"low_quality_proxy_assets":[r for r in mapping_rows if r["mapping_quality"]=="low"],"warnings":["Execution backtest uses ETF proxy qfq prices and only covers tradable ETF periods.","This execution backtest is an ETF proxy validation, not a production trading instruction."]}
    report["decision"]=_decision(report,cfg); return report

def _normalize(rows):
    if not rows or rows[0]["value"]<=0:return []
    base=rows[0]["value"]; return [{"date":r["date"],"value":r["value"]/base} for r in rows]
def _cash_drag(rows): return sum(float(r.get("weights",{}).get("CASH",0)) for r in rows)/len(rows) if rows else 0
def _summary(rows,allocations):
    mapped=[r for r in rows if r["executable"]]; total=sum(sum(v for k,v in a.get("weights",{}).items() if k!="CASH") for a in allocations); covered=sum(sum(a.get("weights",{}).get(r["research_asset_id"],0) for r in mapped) for a in allocations)
    return {"mapped_research_assets":len(mapped),"unmapped_research_assets":len(rows)-len(mapped),"low_quality_proxy_assets":sum(r["mapping_quality"]=="low" for r in rows),"untradable_months":sum(float(a.get("weights",{}).get("CASH",0))>0 for a in allocations),"mapped_weight_coverage":round(covered/total,6) if total else 0}
def _decision(report,cfg):
    metrics=report.get("metrics",{}); summary=report.get("mapping_summary",{}); gap=report.get("execution_gap",{}); reasons=[]
    if summary.get("mapped_weight_coverage",0)<cfg.min_mapped_coverage: reasons.append("mapped weight coverage is below 70%")
    if summary.get("untradable_months",0)>20: reasons.append("untradable months exceed 20")
    if metrics.get("max_drawdown",0)<=-.40: reasons.append("execution max drawdown is not above -40%")
    if metrics.get("sharpe",0)<=.25: reasons.append("execution Sharpe is not above 0.25")
    if gap.get("annual_return_gap",0)<=-.08: reasons.append("annual return gap is not above -8%")
    return {"ready_for_execution_validation":not reasons,"reasons":reasons,"warning":"This is not production approval or a trading instruction."}
