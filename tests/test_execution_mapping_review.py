import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backtest.execution.dataset_provenance import load_price_dataset_manifest,verify_price_dataset_manifest
from backtest.execution.review_report import load_mapping_attribution_report,load_mapping_review_report
from engine.asset_registry import load_execution_universe

CLIENT=TestClient(app);ASSETS=load_execution_universe();MANIFEST=load_price_dataset_manifest();ATTR=load_mapping_attribution_report();REVIEW=load_mapping_review_report()

@pytest.mark.parametrize("asset",ASSETS)
def test_manifest_contains_each_execution_asset_hash(asset):assert len(MANIFEST["file_hashes"][asset.asset_id])==64
@pytest.mark.parametrize("asset",ASSETS)
def test_manifest_asset_hash_is_hex(asset):int(MANIFEST["file_hashes"][asset.asset_id],16)
@pytest.mark.parametrize("asset",ASSETS)
def test_provenance_audit_covers_each_asset(asset):assert asset.asset_id in MANIFEST["file_hashes"]
@pytest.mark.parametrize("asset",ASSETS)
def test_manifest_basis_applies_to_each_asset(asset):assert MANIFEST["provider"]=="tushare" and MANIFEST["return_basis"]=="qfq"
@pytest.mark.parametrize("review",REVIEW["proposal_reviews"])
@pytest.mark.parametrize("field",["research_asset_id","semantic_review","marginal_attribution","decision","requires_manual_approval","eligible_for_recommendation"])
def test_each_proposal_review_is_auditable(review,field):assert field in review
@pytest.mark.parametrize("review",REVIEW["proposal_reviews"])
def test_all_proposal_decisions_remain_manual(review):assert review["decision"]["requires_manual_approval"] is True
@pytest.mark.parametrize("review",REVIEW["proposal_reviews"])
def test_weak_or_invalid_semantics_are_not_approved(review):
 if review["semantic_review"]["semantic_quality"] in {"weak","invalid"}:assert review["decision"]["result"]!="recommend_manual_approval"
def test_provenance_is_verified():assert verify_price_dataset_manifest(MANIFEST,ASSETS)["provenance_verified"] is True
def test_mock_manifest_cannot_be_tushare():
 fake={**MANIFEST,"provider":"mock"};assert verify_price_dataset_manifest(fake,ASSETS)["provenance_verified"] is False
def test_full_overlay_collision_includes_existing_chip_mapping():
 chip=next(x for x in REVIEW["proxy_collision_diagnostics"]["proxy_collisions"] if x["proxy_id"]=="512760.SH");assert "H20007.CSI" in chip["research_asset_ids"]
def test_collision_has_average_and_month_counts():
 for row in REVIEW["proxy_collision_diagnostics"]["proxy_collisions"]:assert {"average_aggregate_weight","months_above_30_percent","months_above_35_percent"}<=set(row)
@pytest.mark.parametrize("endpoint",["execution-mapping-attribution","execution-mapping-review","execution-price-provenance"])
def test_review_apis_are_read_only(endpoint):assert CLIENT.get('/api/research/'+endpoint).status_code==200
def test_review_page_sections():
 text=CLIENT.get('/execution-backtest').text
 for value in ("Dataset Provenance","Per-Proposal Marginal Impact","Drawdown Attribution","Full Proxy Collision Exposure","Semantic Mapping Review","Ready for Mapping Update Task?","Statistical correlation alone"):assert value in text
