import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.execution.counterfactual import run_mapping_counterfactual
from backtest.execution.data_loader import load_execution_price_dataset
from backtest.execution.mapping_proposal import proposal_collisions
from backtest.execution.dataset_provenance import load_price_dataset_manifest,verify_price_dataset_manifest
from backtest.execution.proposal_report import COUNTER,PROPOSAL,write_report
from backtest.research.report import load_research_backtest_report
from engine.asset_registry import load_asset_mappings,load_execution_universe
p=argparse.ArgumentParser();p.add_argument('--provider',choices=['local'],default='local');a=p.parse_args();proposal=json.loads(PROPOSAL.read_text(encoding='utf-8'));research=load_research_backtest_report();assets=load_execution_universe();mappings=load_asset_mappings();provenance=verify_price_dataset_manifest(load_price_dataset_manifest(),assets);provider='tushare' if provenance['provenance_verified'] else 'unverified_local';baseline,counter,common,impact=run_mapping_counterfactual(research,mappings,proposal['proposals'],load_execution_price_dataset(assets),assets,data_provider=provider);collisions=proposal_collisions(proposal['proposals'],research['monthly_allocations'],mappings);reasons=[]
if not provenance['provenance_verified']: reasons.append('execution price dataset provenance is not verified')
if counter['mapping_summary']['tradable_weight_coverage']<.85: reasons.append('counterfactual tradable coverage below 85%')
if counter['mapping_summary']['untradable_month_ratio']>.20: reasons.append('counterfactual untradable month ratio above 20%')
if impact['tradable_weight_coverage_delta']<=0: reasons.append('tradable coverage did not improve')
if impact['annual_return_delta']<-.02: reasons.append('annual return declined more than 2%')
if impact['max_drawdown_delta']<-.05: reasons.append('max drawdown worsened more than 5%')
if collisions['has_weight_violation']: reasons.append('single ETF aggregate weight exceeds 35%')
report={"available":True,"data_provider":provider,"dataset_provenance":provenance,"baseline":baseline,"counterfactual":counter,"common_comparison_period":common,"impact":impact,"proxy_collision_diagnostics":collisions,"decision":{"ready_for_manual_mapping_approval":not reasons,"reasons":reasons,"warning":"Counterfactual proposal only; asset_mapping.json has not been modified."}};write_report(report,COUNTER);print({"ready":not reasons,"impact":impact})
