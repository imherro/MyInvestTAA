import pytest

from current_taa.allocation import build_current_allocation, map_index_weights


ASSETS = [
    {"asset_id": "A", "name": "资产A"},
    {"asset_id": "B", "name": "资产B"},
    {"asset_id": "C", "name": "资产C"},
]
MAPPINGS = [
    {"research_asset_id": "A", "etf_id": "E1", "etf_name": "ETF一号", "mapping_quality": "high", "notes": "直接映射", "enabled": True},
    {"research_asset_id": "B", "etf_id": "E1", "etf_name": "ETF一号", "mapping_quality": "high", "notes": "同一ETF", "enabled": True},
]


def test_mapped_assets_are_aggregated_by_etf():
    result = map_index_weights({"A": 0.3, "B": 0.2, "CASH": 0.5}, ASSETS, MAPPINGS, {"E1": [{"date": "2026-01-01", "close": 1.0}]}, "2026-01-01")
    assert result["weights"] == {"E1": 0.5, "CASH": 0.5}
    assert len(result["etfs"][0]["research_assets"]) == 2


def test_missing_mapping_moves_weight_to_cash():
    result = map_index_weights({"C": 0.4, "CASH": 0.6}, ASSETS, MAPPINGS, {}, "2026-01-01")
    assert result["cash_weight"] == 1.0
    assert result["cash_reasons"][0]["reason"] == "没有启用的ETF映射"


def test_missing_current_price_moves_weight_to_cash():
    result = map_index_weights({"A": 1.0}, ASSETS, MAPPINGS, {"E1": [{"date": "2025-12-31", "close": 1.0}]}, "2026-01-01", require_exact_date=True)
    assert result["weights"] == {"CASH": 1.0}
    assert "没有有效前复权价格" in result["cash_reasons"][0]["reason"]


def test_weight_sum_is_checked():
    result = map_index_weights({"A": 0.4, "CASH": 0.6}, ASSETS, MAPPINGS, {"E1": [{"date": "2026-01-01", "close": 1.0}]}, "2026-01-01")
    assert result["weight_sum"] == pytest.approx(1.0)
    assert result["weight_sum_valid"] is True


def test_current_allocation_contains_names_and_no_trade_fields():
    research = {"model": "CURRENT_TAA", "period": {"end": "2026-01-02"}, "monthly_allocations": [{"signal_date": "2025-12-31", "effective_date": "2026-01-02", "weights": {"A": 1.0}}]}
    report = build_current_allocation(research, ASSETS, MAPPINGS, {"E1": [{"date": "2026-01-02", "close": 1.0}]})
    assert report["index_target_weights"][0]["name"] == "资产A"
    assert report["etf_target_weights"][0]["etf_name"] == "ETF一号"
    assert report["trading_instruction"] is False
