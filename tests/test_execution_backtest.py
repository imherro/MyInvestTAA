from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from backtest.execution.data_loader import build_mock_execution_price_dataset
from backtest.execution.engine import run_execution_backtest
from backtest.execution.mapping import build_execution_mapping
from backtest.execution.models import ExecutionBacktestConfig
from backtest.execution.report import load_execution_backtest_report, write_execution_backtest_report
from backtest.research.report import load_research_backtest_report
from backend.main import app
from engine.asset_registry import load_asset_mappings, load_execution_universe

CLIENT=TestClient(app); ASSETS=load_execution_universe(); MAPPINGS=load_asset_mappings(); RESEARCH=load_research_backtest_report(); DATA=build_mock_execution_price_dataset(ASSETS); REPORT=run_execution_backtest(RESEARCH,DATA,MAPPINGS,ASSETS)

def test_execution_report_is_available(): assert REPORT['available'] is True
def test_execution_report_uses_proxy_strategy(): assert REPORT['strategy']=='EXECUTION_PROXY_MVP'
def test_execution_period_is_not_before_research_period(): assert REPORT['period']['start']>=RESEARCH['period']['start']
def test_execution_period_respects_new_energy_etf_start(): assert REPORT['period']['start']>='2021-01-22'
def test_execution_has_overlap_metrics_and_gap(): assert REPORT['research_overlap_metrics'] and 'annual_return_gap' in REPORT['execution_gap']
def test_execution_report_warns_not_production(): assert any('not a production trading instruction' in x for x in REPORT['warnings'])
def test_none_mapping_becomes_unmapped(): assert any(x['research_asset_id']=='931743CNY010.CSI' for x in REPORT['unmapped_assets'])
def test_low_quality_mapping_is_excluded_by_default(): assert any(x['reason']=='low_quality_proxy_excluded' for x in REPORT['unmapped_assets'])
def test_low_quality_mapping_can_be_allowed():
 rows=build_execution_mapping(RESEARCH['monthly_allocations'],MAPPINGS,ASSETS,allow_low_quality_proxy=True)
 assert next(x for x in rows if x['research_asset_id']=='H00805.CSI')['executable'] is True
def test_default_mapping_uses_primary_proxy_only():
 rows=build_execution_mapping(RESEARCH['monthly_allocations'],MAPPINGS,ASSETS)
 assert next(x for x in rows if x['research_asset_id']=='H00300.CSI')['proxy_id']=='510300.SH'
def test_execution_weights_keep_cash_for_unmapped_assets(): assert any('CASH' in x['weights'] for x in REPORT['monthly_allocations'])
def test_execution_decision_is_present(): assert 'ready_for_execution_validation' in REPORT['decision']
def test_execution_report_write_and_load(tmp_path):
 path=tmp_path/'execution.json'; write_execution_backtest_report(REPORT,path); assert load_execution_backtest_report(path)['available'] is True
def test_execution_report_missing_file(tmp_path): assert load_execution_backtest_report(tmp_path/'missing.json')['available'] is False
def test_execution_api_reads_local_report(): assert CLIENT.get('/api/research/execution-backtest').status_code==200
def test_execution_page_renders_sections():
 text=CLIENT.get('/execution-backtest').text
 for value in ('Execution Backtest','Execution Gap','Mapping Summary','Ready for Execution Validation?','header.js','footer.js'): assert value in text
def test_execution_api_does_not_call_tushare(monkeypatch):
 monkeypatch.setattr('data_provider.tushare_provider.TushareProvider._client',lambda *a,**k: (_ for _ in ()).throw(AssertionError('no live fetch')))
 assert CLIENT.get('/api/research/execution-backtest').status_code==200

@pytest.mark.parametrize('allocation',REPORT['monthly_allocations'])
def test_each_execution_allocation_is_fully_accounted_for(allocation):
 assert sum(allocation['weights'].values()) <= 1.000001

@pytest.mark.parametrize('allocation',REPORT['monthly_allocations'])
def test_each_execution_allocation_uses_only_etfs_or_cash(allocation):
 valid={asset.asset_id for asset in ASSETS}|{'CASH'}
 assert set(allocation['weights']) <= valid
