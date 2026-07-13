from __future__ import annotations
import argparse, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.execution.data_loader import fetch_execution_price_dataset_with_errors, load_execution_price_dataset
from backtest.execution.mapping_improvement import load_mapping_improvement_report
from backtest.execution.proxy_research import build_proxy_research_report
from backtest.execution.proxy_report import write_proxy_research_report
from backtest.research.data_loader import fetch_research_price_dataset, load_research_price_dataset
from data_provider.tushare_provider import TushareProvider
from engine.asset_registry import load_asset_mappings,load_execution_universe,load_research_universe
def main():
    parser=argparse.ArgumentParser(description="Research ETF proxy candidates from offline or Tushare prices.");parser.add_argument("--provider",choices=["local","tushare"],default="local");parser.add_argument("--start");parser.add_argument("--end");args=parser.parse_args()
    blocked=load_mapping_improvement_report().get("unmapped_research_assets",[])+load_mapping_improvement_report().get("low_quality_proxy_assets",[])
    blocked=list(dict.fromkeys(blocked)); research_assets=[asset for asset in load_research_universe() if asset.asset_id in blocked]; execution_assets=load_execution_universe()
    if args.provider=="local": research_prices=load_research_price_dataset(research_assets); execution_prices=load_execution_price_dataset(execution_assets)
    else:
        research_provider=TushareProvider(return_type="price"); execution_provider=TushareProvider(return_type="qfq")
        if not execution_provider.provider_status()["available"]: raise SystemExit("TUSHARE_TOKEN is required for --provider tushare.")
        research_prices=fetch_research_price_dataset(research_provider,research_assets,args.start,args.end);execution_prices,_=fetch_execution_price_dataset_with_errors(execution_provider,execution_assets,args.start,args.end)
    report=build_proxy_research_report(research_prices,execution_prices,load_asset_mappings(),blocked)
    report.update({"data_provider":args.provider,"candidate_count":len(execution_assets),"blocked_research_assets":blocked,"start":args.start,"end":args.end});target=write_proxy_research_report(report);print({"report":str(target),"assets":len(blocked),"candidates":report["candidate_count"]})
if __name__=="__main__":main()
