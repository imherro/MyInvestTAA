import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.execution.data_loader import build_mock_execution_price_dataset,fetch_execution_price_dataset,load_execution_price_dataset,write_execution_price_dataset
from backtest.execution.engine import run_execution_backtest
from backtest.execution.report import load_execution_backtest_report,write_execution_backtest_report
from backtest.research.report import load_research_backtest_report
from data_provider.tushare_provider import TushareProvider
from engine.asset_registry import load_asset_mappings,load_execution_universe
def main():
 p=argparse.ArgumentParser();p.add_argument('--provider',choices=['local','mock','tushare'],default='local');p.add_argument('--start');p.add_argument('--end');a=p.parse_args(); assets=load_execution_universe()
 if a.provider=='local': data=load_execution_price_dataset(assets)
 elif a.provider=='mock': data=build_mock_execution_price_dataset(assets);write_execution_price_dataset(data)
 else:
  provider=TushareProvider(return_type='qfq')
  if not provider.provider_status()['available']: raise SystemExit('TUSHARE_TOKEN is required for --provider tushare.')
  data=fetch_execution_price_dataset(provider,assets,a.start,a.end);write_execution_price_dataset(data)
 report=run_execution_backtest(load_research_backtest_report(),data,load_asset_mappings(),assets);report['data_provider']=a.provider;write_execution_backtest_report(report);print({'available':report.get('available'),'period':report.get('period'),'metrics':report.get('metrics')})
if __name__=='__main__': main()
