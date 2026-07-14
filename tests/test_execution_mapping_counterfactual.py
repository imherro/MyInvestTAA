import json
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backtest.execution import proposal_report
from backtest.execution.proposal_report import build_counterfactual_baseline_contract, build_counterfactual_input_contract, load_counterfactual_report, load_mapping_proposal_report, validate_counterfactual_payload

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
def test_counterfactual_has_current_baseline_contract():
 assert COUNTER['status']=='current'
 assert COUNTER['evidence_use']=='current_analysis'
 assert COUNTER['baseline_contract_verification']['verified'] is True
 assert COUNTER['input_contract_verification']['verified'] is True
 assert COUNTER['counterfactual_input_contract']['valid'] is True
 assert COUNTER['delta_contract']['delta_unit']=='fraction_point'
 assert COUNTER['delta_contract']['display_unit']=='percentage_points'
def test_legacy_counterfactual_is_historical_only(tmp_path):
 payload=deepcopy(COUNTER);payload.pop('baseline_contract',None)
 path=tmp_path/'legacy-counterfactual.json';path.write_text(json.dumps(payload),encoding='utf-8')
 loaded=load_counterfactual_report(path)
 assert loaded['status']=='stale'
 assert loaded['evidence_use']=='historical_only'
 assert loaded['decision']['ready_for_manual_mapping_approval'] is False
def test_counterfactual_source_hash_drift_is_stale(tmp_path):
 payload=deepcopy(COUNTER);payload['baseline_contract']=build_counterfactual_baseline_contract()
 payload['baseline_contract']['sources']['asset_mapping']['sha256']='0'*64
 path=tmp_path/'drifted-counterfactual.json';path.write_text(json.dumps(payload),encoding='utf-8')
 loaded=load_counterfactual_report(path)
 assert loaded['status']=='stale'
 assert any('asset_mapping' in error for error in loaded['baseline_contract_verification']['errors'])
def test_counterfactual_embedded_baseline_drift_is_stale(tmp_path):
 payload=deepcopy(COUNTER);payload['baseline_contract']=build_counterfactual_baseline_contract()
 payload['baseline']['metrics']['annual_return']=-0.99
 path=tmp_path/'drifted-baseline.json';path.write_text(json.dumps(payload),encoding='utf-8')
 loaded=load_counterfactual_report(path)
 assert loaded['status']=='stale'
 assert any('embedded baseline' in error for error in loaded['baseline_contract_verification']['errors'])
def test_counterfactual_proposal_overlay_drift_is_stale(tmp_path):
 payload=deepcopy(COUNTER);payload['counterfactual_input_contract']=build_counterfactual_input_contract()
 payload['counterfactual_input_contract']['proposal_overlay_semantic_hash']='0'*64
 path=tmp_path/'drifted-overlay.json';path.write_text(json.dumps(payload),encoding='utf-8')
 loaded=load_counterfactual_report(path)
 assert loaded['status']=='stale' and loaded['evidence_use']=='historical_only'
 assert any('overlay semantic hash' in error for error in loaded['input_contract_verification']['errors'])
def test_counterfactual_required_source_missing_is_fail_closed(monkeypatch,tmp_path):
 missing=tmp_path/'missing-execution.json'
 monkeypatch.setitem(proposal_report.COUNTERFACTUAL_BASELINE_SOURCES,'execution_backtest_report',missing)
 monkeypatch.setitem(proposal_report.COUNTERFACTUAL_INPUT_SOURCES,'execution_backtest_report',missing)
 path=tmp_path/'counter.json';path.write_text(json.dumps(COUNTER),encoding='utf-8')
 loaded=load_counterfactual_report(path)
 assert loaded['available'] is True and loaded['status']=='stale' and loaded['evidence_use']=='historical_only'
 assert loaded['decision']['ready_for_manual_mapping_approval'] is False
 assert any('missing' in error for error in loaded['input_contract_verification']['errors'])
def test_counterfactual_required_json_damage_is_fail_closed(monkeypatch,tmp_path):
 damaged=tmp_path/'execution.json';damaged.write_text('{broken',encoding='utf-8')
 monkeypatch.setitem(proposal_report.COUNTERFACTUAL_BASELINE_SOURCES,'execution_backtest_report',damaged)
 monkeypatch.setitem(proposal_report.COUNTERFACTUAL_INPUT_SOURCES,'execution_backtest_report',damaged)
 path=tmp_path/'counter.json';path.write_text(json.dumps(COUNTER),encoding='utf-8')
 loaded=load_counterfactual_report(path)
 assert loaded['available'] is True and loaded['status']=='stale'
 assert any('damaged' in error for error in loaded['input_contract_verification']['errors'])
def test_counterfactual_report_damage_is_unavailable(tmp_path):
 path=tmp_path/'counter.json';path.write_text('{broken',encoding='utf-8')
 loaded=load_counterfactual_report(path)
 assert loaded['available'] is False and loaded['status']=='unavailable'
def test_mutable_counterfactual_scope_mismatch_is_stale(tmp_path):
 payload=deepcopy(COUNTER);payload['release_scope']='committed_release'
 path=tmp_path/'counter.json';path.write_text(json.dumps(payload),encoding='utf-8')
 loaded=load_counterfactual_report(path)
 assert loaded['available'] is True and loaded['status']=='stale'
 assert any('release scope mismatch' in error for error in loaded['validation_errors'])
def test_committed_scope_mismatch_is_unavailable():
 payload=deepcopy(COUNTER);payload['release_scope']='mutable_pre_release'
 loaded=validate_counterfactual_payload(payload,expected_scope='committed_release',committed=True)
 assert loaded['available'] is False and loaded['status']=='unavailable'
def test_counterfactual_api_returns_200_when_committed_release_integrity_fails(monkeypatch):
 monkeypatch.setattr('backend.main.load_committed_counterfactual_report',lambda:{'available':False,'status':'unavailable','evidence_use':'unavailable','message':'committed system release integrity failed'})
 response=CLIENT.get('/api/research/execution-mapping-counterfactual')
 assert response.status_code==200
 assert response.json()['available'] is False
 assert response.json()['message']=='committed system release integrity failed'
def test_proposal_api(): assert CLIENT.get('/api/research/execution-mapping-proposal').status_code==200
def test_counterfactual_api(): assert CLIENT.get('/api/research/execution-mapping-counterfactual').status_code==200
def test_page_sections():
 text=CLIENT.get('/execution-backtest').text
 assert 'Mapping Proposal' in text and 'Baseline vs Counterfactual' in text
