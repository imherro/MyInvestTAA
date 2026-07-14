from copy import deepcopy
import hashlib
import json

from fastapi.testclient import TestClient

from backtest.execution.data_loader import load_execution_price_dataset
from backtest.execution.report import load_execution_backtest_report
from backtest.execution.v2 import load_execution_v2_report, run_execution_backtest_v2
from backtest.execution.v2.calendar import load_trade_calendar
from backtest.execution.v2.investability import load_instrument_metadata
from backtest.research.report import load_research_backtest_report
from backend.main import app
from engine.asset_registry import load_asset_mappings, load_execution_universe


CLIENT = TestClient(app)
ASSETS = load_execution_universe()
MAPPINGS = load_asset_mappings()
RESEARCH = load_research_backtest_report()
V1 = load_execution_backtest_report()
PRICES = load_execution_price_dataset(ASSETS)
CALENDAR = load_trade_calendar()
METADATA = load_instrument_metadata()
REPORT = load_execution_v2_report()


def _run(prices=None, mappings=None, assets=None):
    return run_execution_backtest_v2(
        RESEARCH,
        prices or PRICES,
        mappings or MAPPINGS,
        assets or ASSETS,
        CALENDAR,
        METADATA,
        v1_report=V1,
        data_provider="verified_local_tushare",
    )[0]


def _remove_price(asset_id, date):
    prices = deepcopy(PRICES)
    prices[asset_id] = [row for row in prices[asset_id] if row.date != date]
    return prices


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def test_v2_report_is_experimental_and_not_a_v1_replacement():
    assert REPORT["available"] is True
    assert REPORT["strategy"] == "EXECUTION_PROXY_V2_EXPERIMENTAL"
    assert REPORT["engine_status"] == "experimental_validation_only"
    assert REPORT["eligible_to_replace_v1"] is False
    assert REPORT["production_actionable"] is False


def test_v2_uses_independent_calendar_and_retains_dates_v1_deleted():
    assert REPORT["calendar_contract"]["global_etf_date_intersection_used"] is False
    assert REPORT["periods"]["simulation_calendar_period"]["start"] == "2021-01-14"
    assert REPORT["periods"]["common_v1_comparison_period"]["start"] == "2021-02-04"
    assert REPORT["comparison_to_v1"]["days_retained_that_v1_deleted"] == 16


def test_first_signal_executes_on_next_trade_day_without_lookahead():
    first = REPORT["monthly_allocations"][0]
    assert first["signal_date"] == "2021-01-29"
    assert first["actual_execution_date"] == "2021-02-01"
    assert REPORT["execution_timing_contract"]["same_day_lookahead_allowed"] is False


def test_late_etf_weight_is_cash_before_listing():
    first = REPORT["monthly_allocations"][0]
    assert first["cash_breakdown"]["not_yet_investable_cash"] == 0.1
    detail = next(row for row in first["translation_details"] if row["research_asset_id"] == "H20771.CSI")
    assert detail["destination"] == "CASH"
    assert detail["reason"] == "before_listing"


def test_no_prelisting_or_index_returns_are_substituted():
    assert REPORT["price_availability_contract"]["pre_listing_etf_return_allowed"] is False
    assert REPORT["price_availability_contract"]["index_return_substitution_allowed"] is False
    assert REPORT["validation"]["pre_listing_return_used"] is False
    assert REPORT["validation"]["index_return_substitution_used"] is False


def test_daily_nav_and_weights_reconcile():
    assert REPORT["validation"]["weights_reconcile"] is True
    assert all(row["nav"] > 0 for row in REPORT["daily_portfolio_states"])
    assert all(abs(sum(row["weights"].values()) - 1) < 1e-6 for row in REPORT["daily_portfolio_states"])


def test_b1_cost_slippage_and_cash_yield_are_zero():
    assert REPORT["cost_policy"]["commission_bps"] == 0
    assert REPORT["cost_policy"]["slippage_bps"] == 0
    assert REPORT["transaction_cost_attribution"]["total_transaction_cost"] == 0
    assert REPORT["cash_yield_policy"]["cash_yield"] == 0


def test_v2_emits_no_trade_instruction_fields():
    forbidden = {"order", "orders", "quantity", "quantities", "shares", "amount", "amounts", "target_price"}
    assert forbidden.isdisjoint(set(_walk_keys(REPORT)))


def test_source_manifest_hashes_all_local_inputs_and_price_files():
    manifest = REPORT["source_manifest"]
    price_paths = [key for key in manifest if key.startswith("data/execution_prices/")]
    assert len(price_paths) == len(ASSETS) == 13
    assert all(len(row["sha256"]) == 64 for row in manifest.values())
    assert all(manifest[path]["declared_hash_matches"] is True for path in price_paths)


def test_run_is_deterministic():
    first = _run()
    second = _run()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_mapping_and_asset_order_do_not_change_result():
    reordered = _run(mappings=list(reversed(MAPPINGS)), assets=list(reversed(ASSETS)))
    assert reordered["equity_curve_net"] == REPORT["equity_curve_net"]
    assert reordered["monthly_allocations"] == REPORT["monthly_allocations"]


def test_medium_mapping_is_executable_but_low_quality_and_no_proxy_stay_cash():
    details = [row for event in REPORT["monthly_allocations"] for row in event["translation_details"]]
    assert any(row["research_asset_id"] == "931743CNY010.CSI" and row["destination"] == "512760.SH" for row in details)
    assert any(row["research_asset_id"] == "H00805.CSI" and row["reason"] == "low_quality_excluded" for row in details)
    assert any(row["research_asset_id"] == "H20590.CSI" and row["reason"] == "no_approved_proxy" for row in details)


def test_shared_proxy_targets_equal_translated_weight_sum():
    for event in REPORT["monthly_allocations"]:
        for asset_id, weight in event["weights"].items():
            if asset_id == "CASH":
                continue
            expected = sum(
                row["weight"] for row in event["translation_details"] if row["destination"] == asset_id
            )
            assert abs(weight - expected) < 1e-8


def test_missing_held_price_retains_date_and_freezes_only_that_holding():
    mutated = _run(prices=_remove_price("510300.SH", "2021-03-02"))
    state = next(row for row in mutated["daily_portfolio_states"] if row["date"] == "2021-03-02")
    previous = next(row for row in mutated["daily_portfolio_states"] if row["date"] == "2021-03-01")
    assert state["stale_valuation_assets"] == ["510300.SH"]
    assert state["weights"]["510300.SH"] != 0
    assert state["nav"] != previous["nav"]  # The independently priced 516160.SH still moves.


def test_missing_unheld_entry_price_routes_target_to_cash():
    mutated = _run(prices=_remove_price("510300.SH", "2021-02-01"))
    first = mutated["monthly_allocations"][0]
    assert "510300.SH" not in first["weights"]
    assert first["cash_breakdown"]["missing_entry_price_cash"] == 0.25
    assert first["weights"]["CASH"] == 1.0


def test_metadata_and_calendar_are_verified_local_inputs():
    assert CALENDAR["verified"] is True
    assert CALENDAR["dates"] == sorted(set(CALENDAR["dates"]))
    assert len(METADATA) == 13
    assert all(row["verified"] is True and row["investable_start_date"] for row in METADATA.values())


def test_v1_report_file_is_unchanged():
    digest = hashlib.sha256(open("reports/execution_backtest_report.json", "rb").read()).hexdigest()
    assert digest == REPORT["comparison_to_v1"]["v1_report_sha256"]


def test_v2_api_and_advanced_page_are_read_only_and_clear():
    response = CLIENT.get("/api/research/execution-backtest-v2")
    assert response.status_code == 200
    assert response.json()["production_actionable"] is False
    page = CLIENT.get("/execution-backtest-v2")
    assert page.status_code == 200
    for text in ("实验验证", "V1 仍是正式执行验证口径", "不进入 Current Decision", "header.js", "footer.js"):
        assert text in page.text


def test_v2_is_linked_only_from_advanced_research_validation():
    assert "/execution-backtest-v2" in CLIENT.get("/research-validation").text
    assert "/execution-backtest-v2" not in CLIENT.get("/current-decision").text
    assert "/execution-backtest-v2" not in CLIENT.get("/").text
