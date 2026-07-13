import json
from datetime import date, timedelta
from pathlib import Path

from backtest.execution.models import ExecutionPrice
from engine.asset_registry.loader import ROOT
from engine.asset_registry.routing import get_asset_history
from data.universe import load_china_etf_universe

EXECUTION_PRICE_DIR = ROOT / "data" / "execution_prices"

def price_file(asset_id, data_dir=None): return (data_dir or EXECUTION_PRICE_DIR) / f"{asset_id.replace('.', '_')}.json"
def load_execution_price_dataset(assets, data_dir=None):
    return {asset.asset_id: [ExecutionPrice(asset.asset_id, str(row['date']), float(row['close']), str(row.get('return_basis') or 'qfq')) for row in json.loads(price_file(asset.asset_id, data_dir).read_text(encoding='utf-8'))] if price_file(asset.asset_id, data_dir).exists() else [] for asset in assets}
def write_execution_price_dataset(dataset, data_dir=None):
    target=data_dir or EXECUTION_PRICE_DIR; target.mkdir(parents=True, exist_ok=True)
    for asset_id, rows in dataset.items(): price_file(asset_id,target).write_text(json.dumps([row.as_dict() for row in rows],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def fetch_execution_price_dataset(provider, assets, start=None, end=None):
    return {asset.asset_id:[ExecutionPrice(asset.asset_id,bar.date,bar.close,"qfq") for bar in get_asset_history(provider,asset,start,end) if bar.close is not None] for asset in assets}
def fetch_execution_price_dataset_with_errors(provider, assets, start=None, end=None):
    dataset={}; errors={}
    for asset in assets:
        try: dataset[asset.asset_id]=[ExecutionPrice(asset.asset_id,bar.date,bar.close,"qfq") for bar in get_asset_history(provider,asset,start,end) if bar.close is not None]
        except Exception as exc: dataset[asset.asset_id]=[]; errors[asset.asset_id]=str(exc)
    return dataset,errors
def build_mock_execution_price_dataset(assets, *, periods=3900):
    dates=[]; current=date(2011,1,4)
    while len(dates)<periods:
        if current.weekday()<5: dates.append(current.isoformat())
        current+=timedelta(days=1)
    starts={str(item["id"]): item.get("start_date") for item in load_china_etf_universe()}
    result={}
    for index,asset in enumerate(assets):
        start=asset.investable_start_date or asset.data_start_date or starts.get(asset.asset_id.split(".")[0]) or "2016-01-04"; price=1+index*.03; rows=[]
        for offset,value in enumerate(dates):
            if value<start: continue
            price=max(.1,price*(1+.00025+(index%5)*.00004+((offset%17)-8)*.00005))
            rows.append(ExecutionPrice(asset.asset_id,value,round(price,6)))
        result[asset.asset_id]=rows
    return result
