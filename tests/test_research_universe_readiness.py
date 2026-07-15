from dataclasses import replace

from fastapi.testclient import TestClient
import pytest

import engine.asset_registry.readiness as readiness
from engine.asset_registry import build_research_universe_readiness, load_research_universe
from engine.asset_registry.return_basis_review import MANUAL_REVIEW_ASSET_IDS
from backend.main import app


client = TestClient(app)
RESEARCH_ASSETS = load_research_universe()
RESEARCH_ASSET_IDS = [asset.asset_id for asset in RESEARCH_ASSETS]
PRICE_INDEX_ASSET_IDS = [asset.asset_id for asset in RESEARCH_ASSETS if asset.return_basis == "price_index"]


def test_research_universe_readiness_current_state_is_not_backtest_ready():
    report = build_research_universe_readiness()

    assert report["ready_for_research_backtest"] is False
    assert report["eligible_assets"] == 14
    assert report["checks"]["has_real_tushare_audit"] is True
    assert report["checks"]["metadata_dates_backfilled"] is True
    assert report["checks"]["no_price_index_in_allocation"] is True
    assert report["checks"]["manual_review_assets_excluded"] is True
    assert report["checks"]["has_execution_mapping_report"] is True


def test_research_universe_readiness_blocks_399606():
    report = build_research_universe_readiness()
    blocked = {row["asset_id"]: row for row in report["blocked_assets"]}

    assert blocked["399606.SZ"]["reason"] == "return_basis_manual_review"


def test_research_universe_readiness_warns_on_provider_metadata_mismatch():
    report = build_research_universe_readiness()

    assert any("provider metadata" in warning for warning in report["warnings"])






def test_research_universe_registry_has_dates_backfilled_for_all_assets():
    for asset in load_research_universe():
        assert asset.data_start_date
        assert asset.investable_start_date


@pytest.mark.parametrize("asset_id", RESEARCH_ASSET_IDS)
def test_research_universe_registry_has_dates_backfilled_by_asset(asset_id):
    assets = {asset.asset_id: asset for asset in load_research_universe()}

    assert assets[asset_id].data_start_date
    assert assets[asset_id].investable_start_date


@pytest.mark.parametrize("asset_id", PRICE_INDEX_ASSET_IDS)
def test_price_index_asset_is_monitor_only_by_asset(asset_id):
    assets = {asset.asset_id: asset for asset in load_research_universe()}

    assert assets[asset_id].eligible_for_allocation is False
    assert assets[asset_id].role == "monitor"


def test_research_universe_registry_freezes_manual_review_asset():
    assets = {asset.asset_id: asset for asset in load_research_universe()}

    assert assets["399606.SZ"].eligible_for_allocation is False
    assert "暂不进入主TAA配置" in assets["399606.SZ"].notes


def test_research_universe_registry_keeps_price_index_out_of_allocation():
    for asset in load_research_universe():
        if asset.return_basis == "price_index":
            assert asset.eligible_for_allocation is False


def test_research_universe_registry_has_no_price_index_allocation_assets():
    allocation_assets = [asset for asset in load_research_universe() if asset.eligible_for_allocation]

    assert all(asset.return_basis != "price_index" for asset in allocation_assets)


def test_research_universe_registry_excludes_all_manual_review_assets():
    assets = {asset.asset_id: asset for asset in load_research_universe()}

    for asset_id in MANUAL_REVIEW_ASSET_IDS:
        assert assets[asset_id].eligible_for_allocation is False


def test_readiness_marks_missing_metadata_dates(monkeypatch):
    assets = load_research_universe()
    broken = [replace(assets[0], data_start_date=None), *assets[1:]]
    monkeypatch.setattr(readiness, "load_research_universe", lambda: broken)

    report = readiness.build_research_universe_readiness()

    assert report["checks"]["metadata_dates_backfilled"] is False
    assert report["ready_for_research_backtest"] is False


def test_readiness_marks_price_index_allocation_failure(monkeypatch):
    assets = load_research_universe()
    changed = [
        replace(asset, eligible_for_allocation=True) if asset.return_basis == "price_index" else asset
        for asset in assets
    ]
    monkeypatch.setattr(readiness, "load_research_universe", lambda: changed)

    report = readiness.build_research_universe_readiness()

    assert report["checks"]["no_price_index_in_allocation"] is False


def test_readiness_marks_manual_review_allocation_failure(monkeypatch):
    assets = load_research_universe()
    changed = [
        replace(asset, eligible_for_allocation=True) if asset.asset_id == "399606.SZ" else asset
        for asset in assets
    ]
    monkeypatch.setattr(readiness, "load_research_universe", lambda: changed)

    report = readiness.build_research_universe_readiness()

    assert report["checks"]["manual_review_assets_excluded"] is False


def test_readiness_marks_missing_real_audit(monkeypatch):
    monkeypatch.setattr(readiness, "load_research_data_availability_report", lambda **kwargs: {"available": False})

    report = readiness.build_research_universe_readiness()

    assert report["checks"]["has_real_tushare_audit"] is False


def test_readiness_marks_missing_mapping_report(monkeypatch):
    monkeypatch.setattr(readiness, "load_asset_mappings", lambda: [])

    report = readiness.build_research_universe_readiness()

    assert report["checks"]["has_execution_mapping_report"] is False


def test_readiness_adds_unavailable_audit_assets_to_blocked(monkeypatch):
    audit = {
        "available": True,
        "provider": "tushare",
        "rows": [
            {
                "asset_id": "H00300.CSI",
                "name": "沪深300收益",
                "available": False,
                "error": "unit unavailable",
            }
        ],
    }
    monkeypatch.setattr(readiness, "load_research_data_availability_report", lambda **kwargs: audit)

    report = readiness.build_research_universe_readiness()

    assert {"asset_id": "H00300.CSI", "name": "沪深300收益", "reason": "unit unavailable"} in report["blocked_assets"]
