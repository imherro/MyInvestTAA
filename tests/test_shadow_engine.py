from current_taa.shadow import build_shadow


ASSETS = [{"asset_id": "A", "name": "资产A"}]
MAPPINGS = [{"research_asset_id": "A", "etf_id": "E1", "etf_name": "ETF一号", "mapping_quality": "high", "notes": "直接映射", "enabled": True}]
DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-02-02", "2026-02-03"]
RESEARCH = {
    "model": "CURRENT_TAA",
    "period": {"end": "2026-02-03"},
    "monthly_allocations": [
        {"signal_date": "2025-12-31", "effective_date": "2026-01-02", "weights": {"A": 1.0}},
        {"signal_date": "2026-01-30", "effective_date": "2026-02-02", "weights": {"A": 0.5, "CASH": 0.5}},
    ],
}
PRICES = {
    "E1": [{"date": date, "close": close} for date, close in zip(DATES, [10, 11, 12, 12, 13])],
    "510500.SH": [{"date": date, "close": close} for date, close in zip(DATES, [20, 21, 22, 23, 24])],
}


def test_shadow_has_no_data_before_activation():
    report = build_shadow(RESEARCH, ASSETS, MAPPINGS, PRICES, DATES, "2026-01-05")
    assert report["equity_curve"][0] == {"date": "2026-01-05", "value": 1.0}
    assert all(row["date"] >= "2026-01-05" for row in report["equity_curve"])


def test_shadow_and_background_start_together_at_one():
    report = build_shadow(RESEARCH, ASSETS, MAPPINGS, PRICES, DATES, "2026-01-02")
    assert report["equity_curve"][0] == report["background_benchmark"]["equity_curve"][0]
    assert report["background_benchmark"]["role"].startswith("同期市场背景基准")


def test_month_end_signal_executes_on_recorded_next_trade_date():
    report = build_shadow(RESEARCH, ASSETS, MAPPINGS, PRICES, DATES, "2026-01-02")
    assert report["rebalance_records"][1]["signal_date"] == "2026-01-30"
    assert report["rebalance_records"][1]["execution_date"] == "2026-02-02"


def test_missing_etf_price_on_rebalance_moves_target_to_cash():
    prices = {**PRICES, "E1": [row for row in PRICES["E1"] if row["date"] != "2026-02-02"]}
    report = build_shadow(RESEARCH, ASSETS, MAPPINGS, prices, DATES, "2026-01-02")
    assert report["rebalance_records"][1]["weights"] == {"CASH": 1.0}


def test_shadow_uses_qfq_disclosure_and_no_index_substitution():
    report = build_shadow(RESEARCH, ASSETS, MAPPINGS, PRICES, DATES, "2026-01-02")
    assert report["return_basis"] == "qfq"
    assert any("前复权" in text for text in report["disclosures"])
