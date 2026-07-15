import pytest
from fastapi.testclient import TestClient

from backtest.execution.data_loader import build_mock_execution_price_dataset
from backtest.execution.engine import run_execution_backtest
from backtest.execution.mapping_improvement import (
    build_mapping_improvement_report,
    load_mapping_improvement_report,
    write_mapping_improvement_report,
)
from backend.main import app
from data.models import PriceBar
from engine.asset_registry import load_asset_mappings, load_execution_universe
from engine.asset_registry.execution_data_audit import (
    build_execution_data_availability_audit,
    load_execution_data_availability_report,
    write_execution_data_availability_audit,
)
from backtest.research.report import load_research_backtest_report


CLIENT = TestClient(app)
ASSETS = load_execution_universe()


class AuditProvider:
    name = "tushare"

    def get_price_history(self, asset_id, start=None, end=None):
        if asset_id == ASSETS[1].asset_id:
            raise RuntimeError("simulated fund_daily failure")
        return [
            PriceBar(asset_id=asset_id, date="2024-01-02", close=1.0, return_type="qfq"),
            PriceBar(asset_id=asset_id, date="2024-01-03", close=1.1, return_type="qfq"),
        ]


AUDIT = build_execution_data_availability_audit(AuditProvider(), "2024-01-01", "2024-01-31")
REPORT = run_execution_backtest(
    load_research_backtest_report(),
    build_mock_execution_price_dataset(ASSETS),
    load_asset_mappings(),
    ASSETS,
    data_provider="mock",
)


@pytest.mark.parametrize("row", AUDIT["rows"])
def test_each_execution_asset_has_required_audit_fields(row):
    assert {"asset_id", "name", "data_api", "return_basis", "available", "row_count", "first_date", "last_date", "error", "warnings"} <= set(row)


@pytest.mark.parametrize("row", AUDIT["rows"])
def test_audit_preserves_qfq_execution_contract(row):
    assert row["data_api"] == "fund_daily"
    assert row["return_basis"] == "qfq"


@pytest.mark.parametrize("row", AUDIT["rows"])
def test_audit_failure_is_isolated_per_etf(row):
    if row["asset_id"] == ASSETS[1].asset_id:
        assert row["available"] is False
        assert row["error"] == "simulated fund_daily failure"
    else:
        assert row["available"] is True
        assert row["row_count"] == 2


@pytest.mark.parametrize("allocation", REPORT["monthly_allocations"])
def test_cash_breakdown_has_all_execution_blockage_categories(allocation):
    assert set(allocation["cash_breakdown"]) == {
        "research_cash", "unmapped_cash", "low_quality_proxy_cash", "missing_price_cash", "untradable_cash"
    }


@pytest.mark.parametrize("key", ["research_cash", "unmapped_cash", "low_quality_proxy_cash", "missing_price_cash", "untradable_cash"])
def test_aggregate_cash_breakdown_has_every_category(key):
    assert key in REPORT["aggregate_cash_breakdown"]


def test_audit_counts_partial_failure_without_stopping():
    assert AUDIT["checked_assets"] == len(ASSETS)
    assert AUDIT["available_assets"] == len(ASSETS) - 1
    assert AUDIT["unavailable_assets"] == 1


def test_audit_write_and_load(tmp_path):
    path = write_execution_data_availability_audit(AUDIT, tmp_path / "audit.json")
    assert load_execution_data_availability_report(path)["available"] is True


def test_audit_missing_file_is_explicit(tmp_path):
    assert load_execution_data_availability_report(tmp_path / "missing.json")["available"] is False


def test_mock_report_cannot_be_real_execution_validation():
    assert REPORT["decision"]["ready_for_execution_validation"] is False
    assert "mock data provider cannot support real execution validation" in REPORT["decision"]["reasons"]


def test_mock_report_has_required_warning():
    assert "This is a mock execution report. It validates mechanics only and is not real ETF execution evidence." in REPORT["warnings"]


def test_mapping_improvement_is_suggestions_only(tmp_path):
    improvement = build_mapping_improvement_report(REPORT)
    path = write_mapping_improvement_report(improvement, tmp_path / "improvement.json")
    assert load_mapping_improvement_report(path)["available"] is True
    assert "not modified automatically" in improvement["warning"]
