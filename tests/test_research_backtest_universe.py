from dataclasses import replace
from pathlib import Path

import pytest

from backtest.research.data_loader import load_research_price_dataset
from backtest.research.universe import (
    load_research_backtest_universe,
    validate_research_backtest_inputs,
)
from engine.asset_registry import load_research_universe


RESEARCH_ASSETS = load_research_universe()
BACKTEST_ASSETS = load_research_backtest_universe()
BACKTEST_IDS = [asset.asset_id for asset in BACKTEST_ASSETS]
PRICE_INDEX_IDS = [asset.asset_id for asset in RESEARCH_ASSETS if asset.return_basis == "price_index"]


def test_research_backtest_universe_has_expected_count():
    assert len(BACKTEST_ASSETS) == 13


def test_research_backtest_universe_excludes_399606():
    assert "399606.SZ" not in BACKTEST_IDS


def test_research_backtest_universe_excludes_price_index_assets():
    assert all(asset.return_basis != "price_index" for asset in BACKTEST_ASSETS)


def test_research_backtest_universe_excludes_industry_monitor_assets():
    assert all(asset.category != "industry" for asset in BACKTEST_ASSETS)
    assert all(asset.sleeve != "industry_monitor" for asset in BACKTEST_ASSETS)


@pytest.mark.parametrize("asset_id", BACKTEST_IDS)
def test_research_backtest_universe_asset_has_dates(asset_id):
    assets = {asset.asset_id: asset for asset in BACKTEST_ASSETS}

    assert assets[asset_id].data_start_date
    assert assets[asset_id].investable_start_date


@pytest.mark.parametrize("asset_id", PRICE_INDEX_IDS)
def test_research_backtest_universe_excludes_each_price_index_asset(asset_id):
    assert asset_id not in BACKTEST_IDS


@pytest.mark.parametrize("asset_id", BACKTEST_IDS)
def test_research_price_file_exists_for_each_backtest_asset(asset_id):
    assert Path(f"data/research_prices/{asset_id.replace('.', '_')}.json").exists()


def test_validate_research_backtest_inputs_accepts_current_dataset():
    price_data = load_research_price_dataset(BACKTEST_ASSETS)

    result = validate_research_backtest_inputs(BACKTEST_ASSETS, price_data)

    assert result["valid"] is True
    assert len(result["valid_assets"]) == 13


def test_validate_research_backtest_inputs_records_missing_price_data():
    price_data = load_research_price_dataset(BACKTEST_ASSETS)
    price_data[BACKTEST_ASSETS[0].asset_id] = []

    result = validate_research_backtest_inputs(BACKTEST_ASSETS, price_data)

    assert result["valid"] is True
    assert result["unavailable_assets"][0]["reason"] == "missing_price_data"


def test_validate_research_backtest_inputs_requires_minimum_assets():
    result = validate_research_backtest_inputs(BACKTEST_ASSETS[:4], {}, min_assets=5)

    assert result["valid"] is False
    assert "at least 5" in result["errors"][0]


def test_validate_research_backtest_inputs_rejects_ineligible_asset():
    asset = replace(BACKTEST_ASSETS[0], eligible_for_allocation=False)

    result = validate_research_backtest_inputs([asset], {asset.asset_id: [object()]}, min_assets=1)

    assert result["excluded_assets"][0]["reason"] == "not_eligible_for_allocation"


def test_validate_research_backtest_inputs_rejects_blocked_asset():
    asset = BACKTEST_ASSETS[0]
    readiness = {"blocked_assets": [{"asset_id": asset.asset_id}]}

    result = validate_research_backtest_inputs([asset], {asset.asset_id: [object()]}, readiness, min_assets=1)

    assert result["excluded_assets"][0]["reason"] == "readiness_blocked"


def test_validate_research_backtest_inputs_rejects_missing_dates():
    asset = replace(BACKTEST_ASSETS[0], data_start_date=None)

    result = validate_research_backtest_inputs([asset], {asset.asset_id: [object()]}, min_assets=1)

    assert result["excluded_assets"][0]["reason"] == "missing_metadata_dates"


def test_validate_research_backtest_inputs_rejects_price_index():
    price_index_asset = next(asset for asset in RESEARCH_ASSETS if asset.return_basis == "price_index")

    result = validate_research_backtest_inputs([price_index_asset], {price_index_asset.asset_id: [object()]}, min_assets=1)

    assert result["excluded_assets"][0]["reason"] == "not_eligible_for_allocation"


def test_validate_research_backtest_inputs_warns_about_research_basis():
    price_data = load_research_price_dataset(BACKTEST_ASSETS)

    result = validate_research_backtest_inputs(BACKTEST_ASSETS, price_data)

    assert "not ETF execution prices" in result["warnings"][0]
