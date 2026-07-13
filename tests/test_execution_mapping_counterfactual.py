import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backtest.execution.proposal_report import load_counterfactual_report, load_mapping_proposal_report

CLIENT=TestClient(app); PROPOSAL=load_mapping_proposal_report(); COUNTER=load_counterfactual_report()

@pytest.mark.parametrize("proposal",PROPOSAL["proposals"])
def test_proposals_are_eligible_and_manual(proposal): assert proposal["eligible_for_recommendation"] and proposal["requires_manual_approval"]
@pytest.mark.parametrize("proposal",PROPOSAL["proposals"])
def test_proposal_has_candidate_evidence(proposal): assert proposal["overlap_days"]>=500 and proposal["correlation"]>=.65 and proposal["tracking_error_annualized"]<=.30
@pytest.mark.parametrize("proposal",PROPOSAL["proposals"])
@pytest.mark.parametrize("field",["research_asset_id","current_primary_execution_proxy","proposed_primary_execution_proxy","current_mapping_quality","proposed_mapping_quality","candidate_score","correlation","tracking_error_annualized","overlap_days","eligible_for_recommendation"])
def test_proposal_fields_are_auditable(proposal,field): assert field in proposal
@pytest.mark.parametrize("key",["tradable_weight_coverage_delta","untradable_month_ratio_delta","annual_return_delta","max_drawdown_delta","sharpe_delta","cash_drag_delta"])
def test_counterfactual_has_impact(key): assert key in COUNTER["impact"]
@pytest.mark.parametrize("key",["baseline","counterfactual"])
def test_common_metrics_exist(key): assert COUNTER[key]["common_period_metrics"]
@pytest.mark.parametrize("item",COUNTER["proxy_collision_diagnostics"]["proxy_collisions"])
def test_collision_is_auditable(item): assert {"proxy_id","research_asset_ids","max_aggregate_weight","violation"}<=set(item)
def test_counterfactual_is_not_manual_approval(): assert COUNTER["decision"]["ready_for_manual_mapping_approval"] is False
def test_proposal_api(): assert CLIENT.get('/api/research/execution-mapping-proposal').status_code==200
def test_counterfactual_api(): assert CLIENT.get('/api/research/execution-mapping-counterfactual').status_code==200
def test_page_sections():
 text=CLIENT.get('/execution-backtest').text
 assert 'Mapping Proposal' in text and 'Baseline vs Counterfactual' in text
