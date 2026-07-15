from backtest.execution.gap import build_execution_gap
from backtest.execution.mapping import build_execution_mapping
from backtest.execution.models import ExecutionBacktestConfig
from backtest.research.metrics import build_metrics
from statistics import median

def run_execution_backtest(research_report, execution_price_data, mappings, execution_universe, *, config=None, data_provider="unknown"):
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
        weights={}; cash_breakdown={"research_cash":float(allocation.get("weights",{}).get("CASH",0)),"unmapped_cash":0.0,"low_quality_proxy_cash":0.0,"missing_price_cash":0.0,"untradable_cash":0.0}
        for research_id,weight in allocation.get("weights",{}).items():
            if research_id=="CASH": continue
            row=by_research.get(research_id); proxy=row.get("proxy_id") if row else None
            if proxy and allocation["date"] in date_maps.get(proxy,{}): weights[proxy]=weights.get(proxy,0)+float(weight)
            elif row and row.get("mapping_quality")=="low": cash_breakdown["low_quality_proxy_cash"]+=float(weight)
            elif not row or not row.get("proxy_id"): cash_breakdown["unmapped_cash"]+=float(weight)
            elif not execution_price_data.get(proxy): cash_breakdown["missing_price_cash"]+=float(weight)
            else: cash_breakdown["untradable_cash"]+=float(weight)
        cash=sum(cash_breakdown.values())
        if cash>1e-10: weights["CASH"]=round(cash,10)
        translated.append({"date":allocation["date"],"weights":weights,"cash_breakdown":{key:round(value,10) for key,value in cash_breakdown.items()}})
    curve=[{"date":dates[0],"value":1.0}]; current={"CASH":1.0}; allocation_index=0
    for index in range(1,len(dates)):
        while allocation_index<len(translated) and translated[allocation_index]["date"]<=dates[index-1]: current=translated[allocation_index]["weights"]; allocation_index+=1
        daily=sum(weight*(date_maps[proxy][dates[index]]/date_maps[proxy][dates[index-1]]-1) for proxy,weight in current.items() if proxy!="CASH" and date_maps[proxy][dates[index-1]]>0)
        curve.append({"date":dates[index],"value":round(curve[-1]["value"]*(1+daily),8)})
    research_curve=[row for row in research_report.get("equity_curve",[]) if row["date"]>=dates[0] and row["date"]<=dates[-1]]; research_overlap=_normalize(research_curve)
    execution_metrics=build_metrics(curve); research_metrics=build_metrics(research_overlap)
    summary=_summary(mapping_rows,allocations,translated); gap=build_execution_gap(research_metrics,execution_metrics)
    non_executable=[r for r in mapping_rows if not r["executable"]]
    no_proxy=[r for r in non_executable if r.get("mapping_quality")=="none"]
    low_quality=[r for r in non_executable if r.get("mapping_quality")=="low"]
    report={"available":True,"strategy":cfg.strategy,"data_provider":data_provider,"source_research_strategy":research_report.get("strategy"),"period":{"start":dates[0],"end":dates[-1]},"metrics":execution_metrics,"equity_curve":curve,"benchmark":_benchmark_curve("510500.SH","南方中证500ETF",dates,date_maps),"monthly_allocations":translated,"source_research_allocations":allocations,"research_full_period_metrics":research_report.get("metrics",{}),"research_overlap_metrics":research_metrics,"execution_gap":{**gap,"cash_drag_gap":round(_cash_drag(translated)-_cash_drag(allocations),6)},"mapping_summary":summary,"aggregate_cash_breakdown":_aggregate_cash_breakdown(translated),"non_executable_assets":non_executable,"unmapped_assets":no_proxy,"low_quality_proxy_assets":low_quality,"warnings":["Execution backtest uses ETF proxy qfq prices and only covers tradable ETF periods.","This execution backtest is an ETF proxy validation, not a production trading instruction."]}
    if data_provider == "mock": report["warnings"].append("This is a mock execution report. It validates mechanics only and is not real ETF execution evidence.")
    elif data_provider == "tushare": report["warnings"].append("This report uses Tushare ETF qfq price data.")
    report["decision"]=_decision(report,cfg); return report

def _normalize(rows):
    if not rows or rows[0]["value"]<=0:return []
    base=rows[0]["value"]; return [{"date":r["date"],"value":r["value"]/base} for r in rows]
def _cash_drag(rows): return sum(float(r.get("weights",{}).get("CASH",0)) for r in rows)/len(rows) if rows else 0
def _benchmark_curve(asset_id,name,dates,date_maps):
    values=date_maps.get(asset_id,{})
    usable=[date for date in dates if date in values and values[date]>0]
    if not usable:return {"asset_id":asset_id,"name":name,"available":False,"reason":"benchmark price history is unavailable"}
    base=values[usable[0]]
    return {"asset_id":asset_id,"name":name,"available":True,"return_basis":"qfq","period":{"start":usable[0],"end":usable[-1]},"points":[{"date":date,"value":round(values[date]/base,8)} for date in usable]}
def _summary(rows,allocations,translated=None):
    mapped=[r for r in rows if r["executable"]]; total=sum(sum(v for k,v in a.get("weights",{}).items() if k!="CASH") for a in allocations); covered=sum(sum(a.get("weights",{}).get(r["research_asset_id"],0) for r in mapped) for a in allocations)
    executable_ids=sorted(r["research_asset_id"] for r in rows if r["executable"])
    non_executable_ids=sorted(r["research_asset_id"] for r in rows if not r["executable"])
    no_proxy_ids=sorted(r["research_asset_id"] for r in rows if not r["executable"] and r.get("mapping_quality")=="none")
    low_quality_ids=sorted(r["research_asset_id"] for r in rows if not r["executable"] and r.get("mapping_quality")=="low")
    translated=translated or []
    gap_keys=("unmapped_cash","low_quality_proxy_cash","missing_price_cash","untradable_cash")
    gap_weights=[sum(float(row.get("cash_breakdown",{}).get(key,0)) for key in gap_keys) for row in translated]
    untradable=[row for row,gap_weight in zip(translated,gap_weights) if gap_weight>1e-10]
    tradable=sum(sum(weight for asset_id,weight in row.get("weights",{}).items() if asset_id!="CASH") for row in translated)
    total_portfolio=sum(sum(float(weight) for weight in allocation.get("weights",{}).values()) for allocation in allocations)
    quality_counts={quality:sum(row.get("mapping_quality")==quality for row in rows) for quality in ("high","medium","low","none")}
    reason_breakdown={}
    for key in gap_keys:
        values=[float(row.get("cash_breakdown",{}).get(key,0)) for row in translated]
        affected=sum(value>1e-10 for value in values)
        reason_breakdown[key]={
            "average_weight":round(sum(values)/len(values),6) if values else 0.0,
            "max_weight":round(max(values),6) if values else 0.0,
            "affected_months":affected,
            "affected_month_ratio":round(affected/len(values),6) if values else 0.0,
        }
    return {
        "mapping_summary_schema_version":"2.0",
        "executable_research_asset_count":len(executable_ids),
        "non_executable_research_asset_count":len(non_executable_ids),
        "no_approved_proxy_asset_count":len(no_proxy_ids),
        "low_quality_excluded_asset_count":len(low_quality_ids),
        "executable_research_asset_ids":executable_ids,
        "non_executable_research_asset_ids":non_executable_ids,
        "no_approved_proxy_asset_ids":no_proxy_ids,
        "low_quality_excluded_asset_ids":low_quality_ids,
        "legacy_metrics":{
            "mapped_research_assets":{"value":len(mapped),"deprecated":True,"replacement":"executable_research_asset_count"},
            "unmapped_research_assets":{"value":len(rows)-len(mapped),"deprecated":True,"legacy_semantics":"non_executable_research_asset_count","replacement":"non_executable_research_asset_count"},
            "low_quality_proxy_assets":{"value":len(low_quality_ids),"deprecated":True,"replacement":"low_quality_excluded_asset_count"},
        },
        "untradable_months":len(untradable),
        "untradable_month_ratio":round(len(untradable)/len(translated),6) if translated else 0,
        "binary_any_gap_month_ratio":round(len(untradable)/len(translated),6) if translated else 0,
        "mapping_weight_coverage":round(covered/total,6) if total else 0,
        "tradable_weight_coverage":round(tradable/total,6) if total else 0,
        "tradable_weight_coverage_total_portfolio":round(tradable/total_portfolio,6) if total_portfolio else 0,
        "coverage_contract":{
            "schema_version":"2.0",
            "metrics":[
                {"metric":"tradable_weight_coverage","numerator":"tradable_translated_weight","denominator":"non_cash_research_weight","numerator_weight_period_sum":round(tradable,10),"denominator_weight_period_sum":round(total,10),"formula":"tradable_translated_weight / non_cash_research_weight","unit":"fraction"},
                {"metric":"tradable_weight_coverage_total_portfolio","numerator":"tradable_translated_weight","denominator":"total_research_portfolio_weight","numerator_weight_period_sum":round(tradable,10),"denominator_weight_period_sum":round(total_portfolio,10),"formula":"tradable_translated_weight / total_research_portfolio_weight","unit":"fraction"},
            ],
        },
        "gap_metrics":{
            "definition":"monthly weight routed to cash because it is unmapped, low quality, missing a price, or otherwise untradable",
            "average_gap_weight":round(sum(gap_weights)/len(gap_weights),6) if gap_weights else 0.0,
            "median_gap_weight":round(median(gap_weights),6) if gap_weights else 0.0,
            "max_gap_weight":round(max(gap_weights),6) if gap_weights else 0.0,
            "gap_month_ratio_gt_1pct":round(sum(value>.01 for value in gap_weights)/len(gap_weights),6) if gap_weights else 0.0,
            "gap_month_ratio_gt_5pct":round(sum(value>.05 for value in gap_weights)/len(gap_weights),6) if gap_weights else 0.0,
            "gap_month_ratio_gt_10pct":round(sum(value>.10 for value in gap_weights)/len(gap_weights),6) if gap_weights else 0.0,
            "gap_reason_breakdown":reason_breakdown,
        },
        "gap_windows":{
            "full_history":_gap_window(translated),
            "recent_24_months":_gap_window(translated[-24:]),
            "recent_12_months":_gap_window(translated[-12:]),
            "continuous_gap_free_suffix":_gap_free_suffix(translated),
        },
        "mapping_count_scope":{
            "count_scope":"research_assets_present_in_source_allocations",
            "included_asset_ids":sorted(row["research_asset_id"] for row in rows),
            "included_asset_count":len(rows),
            "mapping_quality_counts":quality_counts,
        },
    }
def _gap_weight(row):
    return sum(float(row.get("cash_breakdown",{}).get(key,0)) for key in ("unmapped_cash","low_quality_proxy_cash","missing_price_cash","untradable_cash"))
def _gap_window(rows):
    gaps=[_gap_weight(row) for row in rows]
    return {"start":rows[0]["date"] if rows else None,"end":rows[-1]["date"] if rows else None,"allocation_count":len(rows),"binary_any_gap_month_ratio":round(sum(value>1e-10 for value in gaps)/len(gaps),6) if gaps else 0.0,"average_gap_weight":round(sum(gaps)/len(gaps),6) if gaps else 0.0,"max_gap_weight":round(max(gaps),6) if gaps else 0.0}
def _gap_free_suffix(rows):
    start=len(rows)
    while start>0 and _gap_weight(rows[start-1])<=1e-10:start-=1
    suffix=rows[start:]
    return {"start":suffix[0]["date"] if suffix else None,"end":suffix[-1]["date"] if suffix else None,"allocation_count":len(suffix)}
def _aggregate_cash_breakdown(translated):
    keys=("research_cash","unmapped_cash","low_quality_proxy_cash","missing_price_cash","untradable_cash")
    count=len(translated)
    return {key:round(sum(float(row.get("cash_breakdown",{}).get(key,0)) for row in translated)/count,6) if count else 0.0 for key in keys}
def _decision(report,cfg):
    metrics=report.get("metrics",{}); summary=report.get("mapping_summary",{}); gap=report.get("execution_gap",{}); details=[]
    def add(code,metric,actual,threshold,message,semantic_alias=None):
        row={"code":code,"metric":metric,"actual":actual,"threshold":threshold,"message":message}
        if semantic_alias: row["semantic_alias"]=semantic_alias
        details.append(row)
    if report.get("data_provider") == "mock": add("MOCK_PROVIDER","data_provider",report.get("data_provider"),"non_mock","mock data provider cannot support real execution validation")
    if summary.get("tradable_weight_coverage",0)<cfg.min_mapped_coverage: add("TRADABLE_COVERAGE_BELOW_MIN","tradable_weight_coverage",summary.get("tradable_weight_coverage",0),cfg.min_mapped_coverage,"tradable weight coverage is below 70%")
    if summary.get("untradable_month_ratio",0)>.20: add("ANY_GAP_MONTH_RATIO_ABOVE_MAX","untradable_month_ratio",summary.get("untradable_month_ratio",0),.20,"Months containing any execution-weight gap exceed 20%; this does not mean the whole portfolio was untradable.","binary_any_gap_month_ratio")
    if metrics.get("max_drawdown",0)<=-.40: add("MAX_DRAWDOWN_BELOW_MIN","max_drawdown",metrics.get("max_drawdown",0),-.40,"Execution max drawdown is not above -40%.")
    if metrics.get("sharpe",0)<=.25: add("SHARPE_BELOW_MIN","sharpe",metrics.get("sharpe",0),.25,"Execution Sharpe is not above 0.25.")
    if gap.get("annual_return_gap",0)<=-.08: add("ANNUAL_RETURN_GAP_BELOW_MIN","annual_return_gap",gap.get("annual_return_gap",0),-.08,"Annual return gap is not above -8%.")
    return {"ready_for_execution_validation":not details,"reasons":[row["message"] for row in details],"reason_details":details,"warning":"This is not production approval or a trading instruction."}
