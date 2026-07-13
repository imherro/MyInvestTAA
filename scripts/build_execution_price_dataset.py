import argparse, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from backtest.execution.data_loader import build_mock_execution_price_dataset,fetch_execution_price_dataset,write_execution_price_dataset
from data_provider.tushare_provider import TushareProvider
from engine.asset_registry import load_execution_universe
def main():
 p=argparse.ArgumentParser();p.add_argument('--provider',choices=['mock','tushare'],default='mock');p.add_argument('--start');p.add_argument('--end');a=p.parse_args();assets=load_execution_universe()
 if a.provider=='mock': data=build_mock_execution_price_dataset(assets)
 else:
  provider=TushareProvider(return_type='qfq')
  if not provider.provider_status()['available']: raise SystemExit('TUSHARE_TOKEN is required for --provider tushare.')
  data=fetch_execution_price_dataset(provider,assets,a.start,a.end)
 write_execution_price_dataset(data); print({'provider':a.provider,'assets':len(data)})
if __name__=='__main__': main()
