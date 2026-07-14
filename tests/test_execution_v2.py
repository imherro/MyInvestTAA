from copy import deepcopy
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backtest.execution.data_loader import load_execution_price_dataset
from backtest.execution.report import load_execution_backtest_report
from backtest.execution.v2 import load_execution_v2_report, run_execution_backtest_v2
from backtest.execution.v2.calendar import load_trade_calendar
from backtest.execution.v2.investability import load_instrument_metadata
from backtest.execution.v2 import report as report_io
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


def _synthetic_rebalance(target_weight=0.0, missing_dates=("2021-03-01",), extra_allocations=()):
    prices = deepcopy(PRICES)
    prices["510300.SH"] = [row for row in prices["510300.SH"] if row.date not in missing_dates]
    allocations = [
        {"date": "2021-02-19", "weights": {"H00300.CSI": 0.25, "CASH": 0.75}},
        {"date": "2021-02-26", "weights": {"H00300.CSI": target_weight, "CASH": 1 - target_weight}},
        *extra_allocations,
    ]
    research = {"period": {"start": "2021-02-18", "end": "2021-03-08"}, "monthly_allocations": allocations}
    return run_execution_backtest_v2(
        research, prices, MAPPINGS, ASSETS, CALENDAR, METADATA, v1_report=V1,
        data_provider="synthetic_missing_rebalance",
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
    assert REPORT["periods"]["master_calendar_period"]["start"] == "2021-01-14"
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


@pytest.mark.parametrize("target_weight,direction", [(0.0, "reduce"), (0.1, "reduce"), (0.4, "increase")])
def test_missing_held_asset_on_rebalance_creates_real_pending_and_recovers(target_weight, direction):
    report = _synthetic_rebalance(target_weight)
    event = report["monthly_allocations"][1]
    pending = event["deferred_adjustments"][0]
    assert event["scheduled_execution_date"] == "2021-03-01"
    assert event["actual_execution_date"] == "2021-03-02"
    assert event["execution_status"] == "completed"
    assert pending["status"] == "completed"
    assert pending["direction"] == direction
    assert pending["completed_date"] == "2021-03-02"
    assert pending["deferred_days"] == 1
    assert event["cash_breakdown"]["missing_entry_price_cash"] == 0
    assert event["reconciliation"]["verified"] is True


def test_frozen_position_is_not_double_counted_as_cash_gap():
    report = _synthetic_rebalance(0.0)
    event = report["monthly_allocations"][1]
    frozen_weight = event["actual_post_trade_weights"]["510300.SH"]
    assert frozen_weight > 0
    assert event["cash_breakdown"]["missing_entry_price_cash"] == 0
    assert event["actual_post_trade_cash_weight"] < event["requested_target_weights"]["CASH"]
    assert event["cash_reconciliation"]["cash_reconciliation_error"] == 0
    assert report["gap_metrics"]["frozen_positions_excluded_from_cash_gap"] is True


def test_pending_survives_multiple_missing_days_and_executes_once_on_recovery():
    report = _synthetic_rebalance(0.0, ("2021-03-01", "2021-03-02"))
    pending = report["pending_adjustments"][0]
    assert pending["completed_date"] == "2021-03-03"
    assert pending["deferred_days"] == 2
    states = {row["date"]: row for row in report["daily_portfolio_states"]}
    assert states["2021-03-01"]["stale_valuation_assets"] == ["510300.SH"]
    assert states["2021-03-02"]["stale_valuation_assets"] == ["510300.SH"]
    assert "510300.SH" not in states["2021-03-03"]["weights"]


def test_new_signal_supersedes_old_pending_without_silent_deletion():
    report = _synthetic_rebalance(
        0.0,
        ("2021-03-01", "2021-03-02"),
        ({"date": "2021-03-01", "weights": {"H00300.CSI": 0.1, "CASH": 0.9}},),
    )
    first, second = report["pending_adjustments"]
    assert first["status"] == "superseded"
    assert first["superseded_by_signal_date"] == "2021-03-01"
    assert second["target_weight"] == 0.1
    assert second["status"] == "completed"


def test_exact_shared_comparison_really_uses_identical_observation_grid():
    exact = REPORT["comparison_to_v1"]["exact_shared_observation_dates"]
    assert exact["shared_date_count"] == 1310
    assert exact["v1_observation_count"] == exact["v2_observation_count"] == exact["shared_date_count"]
    assert len(exact["date_set_hash"]) == 64
    aligned = REPORT["comparison_to_v1"]["master_calendar_aligned"]
    assert aligned["aligned_date_count"] == 1311
    assert aligned["carried_forward_v1_days"] == 1
    assert aligned["v1_forward_fill_is_analysis_only"] is True


def test_period_contract_does_not_claim_full_fresh_observation():
    assert "fully_observed_period" not in REPORT["periods"]
    assert REPORT["periods"]["fresh_price_complete_period"]["available"] is False
    assert REPORT["periods"]["portfolio_valuation_period"] == REPORT["periods"]["master_calendar_period"]


def test_never_held_etf_price_gap_does_not_change_nav():
    prices = _remove_price("518880.SH", "2021-03-02")
    mutated = _run(prices=prices)
    assert mutated["equity_curve_net"] == REPORT["equity_curve_net"]


def test_adding_never_held_instrument_does_not_change_nav():
    prices = deepcopy(PRICES)
    metadata = deepcopy(METADATA)
    metadata["999999.SH"] = {
        **next(iter(metadata.values())),
        "instrument_id": "999999.SH",
        "name": "synthetic never-held ETF",
        "listing_date": "2016-01-01",
        "investable_start_date": "2016-01-01",
    }
    sample = deepcopy(PRICES["510300.SH"])
    prices["999999.SH"] = sample
    mutated = run_execution_backtest_v2(
        RESEARCH, prices, MAPPINGS, ASSETS, CALENDAR, metadata, v1_report=V1,
        data_provider="synthetic_unused_candidate",
    )[0]
    assert mutated["equity_curve_net"] == REPORT["equity_curve_net"]


def test_calendar_invalid_date_and_order_fail_closed(tmp_path):
    value = deepcopy(CALENDAR)
    value["dates"] = ["2021-02-30"]
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="valid ISO"):
        load_trade_calendar(path)
    value["dates"] = ["2021-02-02", "2021-02-01"]
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="sorted"):
        load_trade_calendar(path)


def test_metadata_invalid_dates_and_inverted_investable_date_fail_closed(tmp_path):
    rows = list(deepcopy(METADATA).values())
    rows[0]["listing_date"] = "2021-02-30"
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid execution metadata date"):
        load_instrument_metadata(path, {row["instrument_id"] for row in rows})
    rows = list(deepcopy(METADATA).values())
    rows[0]["investable_start_date"] = "2010-01-01"
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid execution metadata contract"):
        load_instrument_metadata(path, {row["instrument_id"] for row in rows})


@pytest.mark.parametrize("target", [report_io.REPORT, report_io.TIMELINE, report_io.COMPARISON])
def test_output_artifact_tamper_makes_api_fail_closed(target):
    original = target.read_bytes()
    try:
        value = json.loads(original)
        value["tampered"] = True
        target.write_text(json.dumps(value), encoding="utf-8")
        response = CLIENT.get("/api/research/execution-backtest-v2")
        assert response.status_code == 200
        assert response.json()["available"] is False
        assert response.json()["status"] == "unavailable"
    finally:
        target.write_bytes(original)


def test_missing_commit_marker_makes_api_fail_closed():
    original = report_io.COMMITTED.read_bytes()
    report_io.COMMITTED.unlink()
    try:
        response = CLIENT.get("/api/research/execution-backtest-v2")
        assert response.status_code == 200
        assert response.json()["available"] is False
    finally:
        report_io.COMMITTED.write_bytes(original)


def test_interrupted_output_promotion_restores_previous_valid_set(monkeypatch):
    targets = (*report_io.ARTIFACTS, report_io.MANIFEST, report_io.COMMITTED)
    before = {path: path.read_bytes() for path in targets}
    timeline = json.loads(report_io.TIMELINE.read_text(encoding="utf-8"))
    calls = {"count": 0}
    original_replace = report_io._replace_file

    def fail_second(source, target):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("synthetic interrupted promotion")
        return original_replace(source, target)

    monkeypatch.setattr(report_io, "_replace_file", fail_second)
    with pytest.raises(OSError, match="synthetic interrupted"):
        report_io.write_execution_v2_outputs(REPORT, timeline, REPORT["comparison_to_v1"])
    assert all(path.read_bytes() == content for path, content in before.items())
    assert report_io.verify_execution_v2_output_set()["verified"] is True


def test_multiple_frozen_assets_reconcile_without_cash_double_counting():
    prices = deepcopy(PRICES)
    for asset_id in ("510300.SH", "516160.SH"):
        prices[asset_id] = [row for row in prices[asset_id] if row.date != "2021-03-01"]
    research = {
        "period": {"start": "2021-02-18", "end": "2021-03-05"},
        "monthly_allocations": [
            {"date": "2021-02-19", "weights": {"H00300.CSI": 0.25, "H20771.CSI": 0.1, "CASH": 0.65}},
            {"date": "2021-02-26", "weights": {"CASH": 1.0}},
        ],
    }
    report = run_execution_backtest_v2(
        research, prices, MAPPINGS, ASSETS, CALENDAR, METADATA, v1_report=V1,
        data_provider="synthetic_multi_frozen",
    )[0]
    event = report["monthly_allocations"][1]
    assert set(event["pending_instrument_ids"]) == set()  # Both completed on the recovery day.
    assert {row["instrument_id"] for row in event["deferred_adjustments"]} == {"510300.SH", "516160.SH"}
    assert all(row["status"] == "completed" for row in event["deferred_adjustments"])
    assert event["cash_breakdown"]["missing_entry_price_cash"] == 0
    assert event["reconciliation"]["verified"] is True


def test_full_price_synthetic_case_matches_independent_reference_nav():
    research = {
        "period": {"start": "2021-02-18", "end": "2021-02-26"},
        "monthly_allocations": [
            {"date": "2021-02-19", "weights": {"H00300.CSI": 0.25, "CASH": 0.75}},
        ],
    }
    report = run_execution_backtest_v2(
        research, PRICES, MAPPINGS, ASSETS, CALENDAR, METADATA, v1_report=V1,
        data_provider="synthetic_reference_parity",
    )[0]
    price_map = {row.date: row.close for row in PRICES["510300.SH"]}
    entry_price = price_map["2021-02-22"]
    for row in report["equity_curve_net"]:
        expected = 1.0 if row["date"] <= "2021-02-22" else 0.75 + 0.25 * price_map[row["date"]] / entry_price
        assert abs(row["value"] - expected) < 1e-7


def test_output_manifest_commits_one_verified_cross_file_set():
    manifest = json.loads(report_io.MANIFEST.read_text(encoding="utf-8"))
    marker = json.loads(report_io.COMMITTED.read_text(encoding="utf-8"))
    assert manifest["verified"] is True
    assert set(manifest["artifacts"]) == {path.name for path in report_io.ARTIFACTS}
    assert all(len(row["sha256"]) == len(row["semantic_sha256"]) == 64 for row in manifest["artifacts"].values())
    assert marker["committed"] is True
    assert marker["output_set_hash"] == manifest["output_set_hash"]
    assert report_io.verify_execution_v2_output_set()["verified"] is True


def test_etf_price_before_listing_date_fails_closed():
    metadata = deepcopy(METADATA)
    metadata["510300.SH"]["listing_date"] = "2020-01-01"
    with pytest.raises(ValueError, match="predates listing_date"):
        run_execution_backtest_v2(
            RESEARCH, PRICES, MAPPINGS, ASSETS, CALENDAR, metadata, v1_report=V1,
            data_provider="synthetic_bad_listing",
        )
