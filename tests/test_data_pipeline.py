import json
import subprocess
import sys

import pytest

from data.models import AssetMetadata, PriceBar
from data_pipeline.importer import _select_assets, build_provider, import_market_data
from data_pipeline.normalizer import price_bars_to_history, stored_prices_to_history
from data_pipeline.scheduler import run_import_job
from data_provider.mock_provider import MockProvider
from storage import MarketDataRepository, StoredPrice, connect_database


def test_price_bars_to_history_sorts_rows():
    history = price_bars_to_history([PriceBar("A", "2024-02-01", 1.1), PriceBar("A", "2024-01-01", 1.0)])

    assert history[0]["date"] == "2024-01-01"


def test_stored_prices_to_history_sorts_rows():
    history = stored_prices_to_history([StoredPrice("A", "2024-02-01", 1.1, "mock"), StoredPrice("A", "2024-01-01", 1.0, "mock")])

    assert history[0]["close"] == 1.0


def test_build_provider_returns_mock():
    assert build_provider("mock").name == "mock"


def test_build_provider_returns_tushare():
    assert build_provider("tushare").name == "tushare"


def test_build_provider_returns_baostock():
    assert build_provider("baostock").name == "baostock"


def test_build_provider_rejects_unknown():
    with pytest.raises(ValueError):
        build_provider("unknown")


def test_select_assets_accepts_short_code_for_tushare_style_metadata():
    selected = _select_assets([AssetMetadata("510300.SH", "沪深300ETF", "etf")], ["510300"])

    assert selected[0].asset_id == "510300"


def test_import_market_data_writes_assets_and_prices():
    repository = MarketDataRepository(connect_database(":memory:"))

    result = import_market_data(MockProvider(), repository, ["510300"])

    assert result["imported_assets"] == 1
    assert repository.get_asset("510300") is not None
    assert len(repository.get_price_history("510300")) > 0


def test_import_market_data_quality_gate_can_fail():
    repository = MarketDataRepository(connect_database(":memory:"))

    with pytest.raises(ValueError):
        import_market_data(MockProvider(), repository, ["510300"], min_quality_score=99)


def test_run_import_job_returns_summary():
    result = run_import_job("mock", ["510300"], database_path=":memory:")

    assert result["provider"] == "mock"
    assert result["imported_assets"] == 1


def test_import_market_data_script_runs_with_mock(tmp_path):
    db_path = tmp_path / "market.sqlite"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/import_market_data.py",
            "--provider",
            "mock",
            "--assets",
            "510300",
            "--database",
            str(db_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["provider"] == "mock"
