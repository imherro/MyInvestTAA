from __future__ import annotations
from dataclasses import replace
from backtest.execution.engine import run_execution_backtest
from backtest.research.metrics import build_metrics

def run_mapping_counterfactual(research_report, baseline_mappings, proposed_mapping_overlay, execution_prices, execution_universe, *, data_provider):
    overlay={row["research_asset_id"]:row for row in proposed_mapping_overlay}
    proposed=[replace(mapping,primary_execution_proxy=overlay[mapping.research_asset_id]["proposed_primary_execution_proxy"],execution_proxies=[overlay[mapping.research_asset_id]["proposed_primary_execution_proxy"]],mapping_quality=overlay[mapping.research_asset_id]["proposed_mapping_quality"]) if mapping.research_asset_id in overlay else mapping for mapping in baseline_mappings]
    known={mapping.research_asset_id for mapping in proposed}
    from engine.asset_registry.models import AssetMapping
    proposed.extend(AssetMapping(row["research_asset_id"],row["research_asset_id"],row["proposed_primary_execution_proxy"],[row["proposed_primary_execution_proxy"]],row["proposed_mapping_quality"],"counterfactual proposal only") for row in proposed_mapping_overlay if row["research_asset_id"] not in known)
    baseline=run_execution_backtest(research_report,execution_prices,baseline_mappings,execution_universe,data_provider=data_provider)
    counter=run_execution_backtest(research_report,execution_prices,proposed,execution_universe,data_provider=data_provider)
    common_start=max(baseline["period"]["start"],counter["period"]["start"]);common_end=min(baseline["period"]["end"],counter["period"]["end"])
    for report in (baseline,counter):
        curve=[x for x in report["equity_curve"] if common_start<=x["date"]<=common_end]; base=curve[0]["value"];report["common_period_metrics"]=build_metrics([{"date":x["date"],"value":x["value"]/base} for x in curve])
    impact={"tradable_weight_coverage_delta":round(counter["mapping_summary"]["tradable_weight_coverage"]-baseline["mapping_summary"]["tradable_weight_coverage"],6),"untradable_month_ratio_delta":round(counter["mapping_summary"]["untradable_month_ratio"]-baseline["mapping_summary"]["untradable_month_ratio"],6),"annual_return_delta":round(counter["common_period_metrics"]["annual_return"]-baseline["common_period_metrics"]["annual_return"],6),"max_drawdown_delta":round(counter["common_period_metrics"]["max_drawdown"]-baseline["common_period_metrics"]["max_drawdown"],6),"sharpe_delta":round(counter["common_period_metrics"]["sharpe"]-baseline["common_period_metrics"]["sharpe"],6),"cash_drag_delta":round(counter["aggregate_cash_breakdown"]["research_cash"]+counter["aggregate_cash_breakdown"]["unmapped_cash"]+counter["aggregate_cash_breakdown"]["low_quality_proxy_cash"]-baseline["aggregate_cash_breakdown"]["research_cash"]-baseline["aggregate_cash_breakdown"]["unmapped_cash"]-baseline["aggregate_cash_breakdown"]["low_quality_proxy_cash"],6)}
    return baseline,counter,{"start":common_start,"end":common_end},impact
