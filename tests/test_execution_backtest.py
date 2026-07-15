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
def test_human_approved_medium_mapping_becomes_executable():
 rows=build_execution_mapping(RESEARCH['monthly_allocations'],MAPPINGS,ASSETS)
 target=next(x for x in rows if x['research_asset_id']=='931743CNY010.CSI')
 assert target['proxy_id']=='512760.SH' and target['mapping_quality']=='medium' and target['executable'] is True
def test_human_approved_low_quality_mapping_is_executable():
 rows=build_execution_mapping(RESEARCH['monthly_allocations'],MAPPINGS,ASSETS)
 for asset_id,proxy in [('931688CNY010.CSI','588200.SH'),('H00805.CSI','512400.SH')]:
  row=next(x for x in rows if x['research_asset_id']==asset_id)
  assert row['executable'] is True and row['proxy_id']==proxy and row['mapping_quality']=='low'
def test_low_quality_mapping_can_be_allowed():
 rows=build_execution_mapping(RESEARCH['monthly_allocations'],MAPPINGS,ASSETS,allow_low_quality_proxy=True)
 assert next(x for x in rows if x['research_asset_id']=='H00805.CSI')['executable'] is True
def test_default_mapping_uses_primary_proxy_only():
 rows=build_execution_mapping(RESEARCH['monthly_allocations'],MAPPINGS,ASSETS)
 assert next(x for x in rows if x['research_asset_id']=='H00300.CSI')['proxy_id']=='510300.SH'
def test_execution_weights_keep_cash_for_unmapped_assets(): assert any('CASH' in x['weights'] for x in REPORT['monthly_allocations'])
def test_execution_decision_is_present(): assert 'ready_for_execution_validation' in REPORT['decision']
def test_execution_coverage_contract_names_both_denominators():
 contract=REPORT['mapping_summary']['coverage_contract']
 assert contract['schema_version']=='2.0'
 assert [row['denominator'] for row in contract['metrics']]==['non_cash_research_weight','total_research_portfolio_weight']
 assert all(row['numerator']=='tradable_translated_weight' and row['unit']=='fraction' for row in contract['metrics'])
 assert REPORT['mapping_summary']['tradable_weight_coverage_total_portfolio'] <= REPORT['mapping_summary']['tradable_weight_coverage']
def test_mapping_summary_v2_separates_non_executable_reasons():
 summary=REPORT['mapping_summary']
 assert summary['mapping_summary_schema_version']=='2.0'
 assert (summary['executable_research_asset_count'],summary['non_executable_research_asset_count'],summary['no_approved_proxy_asset_count'],summary['low_quality_excluded_asset_count'])==(14,0,0,0)
 assert summary['non_executable_research_asset_ids']==[]
def test_legacy_mapping_counts_are_deprecated_and_not_top_level():
 summary=REPORT['mapping_summary']
 assert 'unmapped_research_assets' not in summary
 assert summary['legacy_metrics']['unmapped_research_assets']['deprecated'] is True
def test_execution_reason_details_explain_any_gap_semantics():
 detail=next(row for row in REPORT['decision']['reason_details'] if row['code']=='ANY_GAP_MONTH_RATIO_ABOVE_MAX')
 assert detail['metric']=='untradable_month_ratio'
 assert detail['semantic_alias']=='binary_any_gap_month_ratio'
 assert 'does not mean the whole portfolio was untradable' in detail['message']
def test_execution_gap_metrics_preserve_binary_gate_and_add_severity():
 summary=REPORT['mapping_summary'];gaps=summary['gap_metrics']
 assert summary['binary_any_gap_month_ratio']==summary['untradable_month_ratio']
 assert 0 <= gaps['average_gap_weight'] <= gaps['max_gap_weight'] <= 1
 assert gaps['gap_month_ratio_gt_10pct'] <= gaps['gap_month_ratio_gt_5pct'] <= gaps['gap_month_ratio_gt_1pct'] <= summary['binary_any_gap_month_ratio']
 assert set(gaps['gap_reason_breakdown'])=={'unmapped_cash','low_quality_proxy_cash','missing_price_cash','untradable_cash'}
def test_execution_mapping_counts_have_explicit_scope():
 scope=REPORT['mapping_summary']['mapping_count_scope']
 assert scope['count_scope']=='research_assets_present_in_source_allocations'
 assert scope['included_asset_count']==len(scope['included_asset_ids'])==14
 assert sum(scope['mapping_quality_counts'].values())==14
def test_execution_report_write_and_load(tmp_path):
 path=tmp_path/'execution.json'; write_execution_backtest_report(REPORT,path); assert load_execution_backtest_report(path)['available'] is True
def test_execution_report_missing_file(tmp_path): assert load_execution_backtest_report(tmp_path/'missing.json')['available'] is False

@pytest.mark.parametrize('allocation',REPORT['monthly_allocations'])
def test_each_execution_allocation_is_fully_accounted_for(allocation):
 assert sum(allocation['weights'].values()) <= 1.000001

@pytest.mark.parametrize('allocation',REPORT['monthly_allocations'])
def test_each_execution_allocation_uses_only_etfs_or_cash(allocation):
 valid={asset.asset_id for asset in ASSETS}|{'CASH'}
 assert set(allocation['weights']) <= valid
