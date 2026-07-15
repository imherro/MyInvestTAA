from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from data.models import PriceBar
import engine.asset_registry.data_audit as data_audit
from engine.asset_registry import (
    build_research_data_availability_audit,
    build_research_universe_mock_provider,
    load_research_universe,
    write_research_data_availability_audit,
)
from backend.main import app


client = TestClient(app)
RESEARCH_ASSETS = load_research_universe()
RESEARCH_ASSET_IDS = [asset.asset_id for asset in RESEARCH_ASSETS]
PRICE_INDEX_IDS = [asset.asset_id for asset in RESEARCH_ASSETS if asset.return_basis == "price_index"]


def test_build_research_universe_mock_provider_covers_all_research_assets():
    provider = build_research_universe_mock_provider()

    assert provider.name == "mock"
    assert provider.get_index_history("H00300.CSI")[0].date == "2024-01-02"
    assert provider.get_sw_index_history("801780.SI")[0].date == "2024-01-02"


def test_data_availability_audit_counts_mock_assets():
    report = build_research_data_availability_audit(build_research_universe_mock_provider())

    assert report["provider"] == "mock"
    assert report["checked_assets"] == 33
    assert report["available_assets"] == 33
    assert report["unavailable_assets"] == 0
    assert report["errors"] == []


def test_data_availability_audit_records_data_api_counts():
    report = build_research_data_availability_audit(build_research_universe_mock_provider())

    assert report["data_api_counts"] == {"index_daily": 15, "sw_daily": 18}
    assert report["available_by_data_api"]["index_daily"] == {"available": 15, "unavailable": 0}
    assert report["available_by_data_api"]["sw_daily"] == {"available": 18, "unavailable": 0}


@pytest.mark.parametrize("asset_id", RESEARCH_ASSET_IDS)
def test_mock_data_audit_marks_each_research_asset_available(asset_id):
    report = build_research_data_availability_audit(build_research_universe_mock_provider())
    rows = {row["asset_id"]: row for row in report["rows"]}

    assert rows[asset_id]["available"] is True
    assert rows[asset_id]["row_count"] == 3
    assert rows[asset_id]["first_date"] == "2024-01-02"
    assert rows[asset_id]["last_date"] == "2024-12-31"
    assert rows[asset_id]["provider_return_types"] == [rows[asset_id]["return_basis"]]


@pytest.mark.parametrize("asset_id", PRICE_INDEX_IDS)
def test_data_audit_warns_for_each_price_index_asset(asset_id):
    report = build_research_data_availability_audit(build_research_universe_mock_provider())
    rows = {row["asset_id"]: row for row in report["rows"]}

    assert "price_index excludes dividend reinvestment" in rows[asset_id]["warnings"]


class PriceReturnProvider:
    name = "price_return"

    def get_index_history(self, asset_id, start=None, end=None):
        return [PriceBar(asset_id, "2024-01-02", 1.0, return_type="price")]

    def get_sw_index_history(self, asset_id, start=None, end=None):
        return [PriceBar(asset_id, "2024-01-02", 1.0, return_type="price")]

    def get_price_history(self, asset_id, start=None, end=None):
        return [PriceBar(asset_id, "2024-01-02", 1.0, return_type="price")]

    def get_stock_price_history(self, asset_id, start=None, end=None):
        return [PriceBar(asset_id, "2024-01-02", 1.0, return_type="price")]


def test_data_audit_flags_provider_return_type_mismatch_for_total_return_asset():
    report = build_research_data_availability_audit(PriceReturnProvider(), max_assets=1)
    row = report["rows"][0]

    assert row["asset_id"] == "H00300.CSI"
    assert row["provider_return_types"] == ["price"]
    assert any("provider_return_type differs" in warning for warning in row["warnings"])


def test_data_availability_audit_respects_max_assets():
    report = build_research_data_availability_audit(build_research_universe_mock_provider(), max_assets=5)

    assert report["checked_assets"] == 5
    assert len(report["rows"]) == 5


class FailingProvider:
    name = "failing"

    def get_index_history(self, asset_id, start=None, end=None):
        if asset_id == "H00300.CSI":
            raise RuntimeError("unit failure")
        return [PriceBar(asset_id, "2024-01-02", 1.0)]

    def get_sw_index_history(self, asset_id, start=None, end=None):
        return [PriceBar(asset_id, "2024-01-02", 1.0)]

    def get_price_history(self, asset_id, start=None, end=None):
        return [PriceBar(asset_id, "2024-01-02", 1.0)]

    def get_stock_price_history(self, asset_id, start=None, end=None):
        return [PriceBar(asset_id, "2024-01-02", 1.0)]


def test_data_availability_audit_records_single_asset_failure_without_stopping():
    report = build_research_data_availability_audit(FailingProvider(), max_assets=2)
    rows = {row["asset_id"]: row for row in report["rows"]}

    assert report["checked_assets"] == 2
    assert report["available_assets"] == 1
    assert rows["H00300.CSI"]["available"] is False
    assert rows["H00300.CSI"]["error"] == "unit failure"


class EmptyProvider(FailingProvider):
    name = "empty"

    def get_index_history(self, asset_id, start=None, end=None):
        return []


def test_data_availability_audit_marks_empty_rows_unavailable():
    report = build_research_data_availability_audit(EmptyProvider(), max_assets=1)
    row = report["rows"][0]

    assert row["available"] is False
    assert row["error"] == "no rows returned"
    assert "data_unavailable" in row["warnings"]


def test_write_and_load_research_data_availability_report(tmp_path):
    path = tmp_path / "audit.json"
    report = build_research_data_availability_audit(build_research_universe_mock_provider(), max_assets=1)

    written = write_research_data_availability_audit(report, path)
    loaded = data_audit.load_research_data_availability_report(path)

    assert written == path
    assert loaded["available"] is True
    assert loaded["checked_assets"] == 1


def test_load_research_data_availability_report_missing_file(tmp_path):
    loaded = data_audit.load_research_data_availability_report(tmp_path / "missing.json")

    assert loaded["available"] is False
    assert loaded["message"] == "research universe data audit report not found: missing.json"
