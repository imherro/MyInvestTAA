from backtest.execution.counterfactual import run_mapping_counterfactual
from backtest.execution.drawdown_attribution import drawdown_window

def build_proposal_attribution(research, mappings, proposals, prices, assets, provider):
    rows=[]
    for proposal in proposals:
        baseline,counter,common,impact=run_mapping_counterfactual(research,mappings,[proposal],prices,assets,data_provider=provider)
        baseline_window=drawdown_window(baseline);proposal_window=drawdown_window(counter)
        rows.append({"research_asset_id":proposal["research_asset_id"],"proposed_proxy":proposal["proposed_primary_execution_proxy"],"common_comparison_period":common,"marginal_impact":impact,"drawdown_attribution":{"baseline":baseline_window,"proposal":proposal_window,"etf_return_contributions":_window_contributions(counter,prices,proposal_window),"proposal_marginal_loss_contribution":round(impact["max_drawdown_delta"],6)}})
    baseline,full,common,impact=run_mapping_counterfactual(research,mappings,proposals,prices,assets,data_provider=provider)
    full_window=drawdown_window(full)
    return {"available":True,"proposal_attributions":rows,"full_overlay":{"common_comparison_period":common,"impact":impact,"baseline_drawdown":drawdown_window(baseline),"full_overlay_drawdown":full_window,"etf_return_contributions":_window_contributions(full,prices,full_window),"concentration_or_market_exposure":"increased_mapped_market_exposure" if impact["max_drawdown_delta"]<0 else "no_additional_drawdown"}}

def _window_contributions(report,prices,window):
    maps={asset:{row.date:row.close for row in values} for asset,values in prices.items()};allocations=report.get("monthly_allocations",[]);dates=sorted({date for values in maps.values() for date in values if window["start_date"]<=date<=window["trough_date"]});current={};index=0;result={}
    for left,right in zip(dates,dates[1:]):
        while index<len(allocations) and allocations[index]["date"]<=left:current=allocations[index]["weights"];index+=1
        for asset,weight in current.items():
            if asset=="CASH" or left not in maps.get(asset,{}) or right not in maps.get(asset,{}):continue
            result[asset]=result.get(asset,0)+float(weight)*(maps[asset][right]/maps[asset][left]-1)
    return {key:round(value,6) for key,value in sorted(result.items(),key=lambda item:item[1])}
