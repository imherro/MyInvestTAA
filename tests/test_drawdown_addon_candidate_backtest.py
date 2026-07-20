from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_drawdown_addon_candidate_backtest import (  # noqa: E402
    CANDIDATE_RELATIVE,
    EVENT_DIRECTORY_RELATIVE,
    LEDGER_DIRECTORY_RELATIVE,
    DrawdownAddonBacktestError,
    Signal,
    build_drawdown_addon_candidate_backtest,
    calculate_metrics,
    simulate_overlay,
    simulate_static_benchmark,
)


def _prices(values: list[float]) -> list[dict]:
    return [
        {"date": f"2026-01-{index:02d}", "close": value}
        for index, value in enumerate(values, 1)
    ]


def _initialize(prices: list[dict]) -> Signal:
    date = prices[0]["date"]
    return Signal(date, date, "INITIALIZATION", "initialize", 0.7)


def test_signal_executes_next_trading_day_and_cost_uses_actual_weight() -> None:
    prices = _prices([100.0, 90.0, 95.0])
    signals = [
        _initialize(prices),
        Signal(prices[0]["date"], prices[1]["date"], "E1", "tier_1", 0.8),
    ]
    result = simulate_overlay(prices, signals)

    assert result["trade_log"][1]["execution_date"] == prices[1]["date"]
    assert result["trade_log"][1]["execution_close"] == 90.0
    first_cost = 1.0 * 0.7 * 0.001
    first_post_nav = 1.0 - first_cost
    pre_trade_nav = first_post_nav * (0.7 * 0.9 + 0.3)
    actual_weight = first_post_nav * 0.7 * 0.9 / pre_trade_nav
    expected_cost = pre_trade_nav * abs(0.8 - actual_weight) * 0.001
    assert result["trade_log"][1]["transaction_cost"] == pytest.approx(expected_cost)


def test_same_day_multiple_tiers_are_represented_by_deepest_signal() -> None:
    prices = _prices([100.0, 80.0])
    result = simulate_overlay(
        prices,
        [
            _initialize(prices),
            Signal(prices[0]["date"], prices[1]["date"], "E1", "tier_3", 1.0),
        ],
    )
    assert [trade["action"] for trade in result["trade_log"]] == [
        "initialize",
        "tier_3",
    ]
    assert result["metrics"]["tier_1_trigger_count"] == 0
    assert result["metrics"]["tier_3_trigger_count"] == 1


def test_bounce_does_not_reduce_and_open_event_has_no_reset() -> None:
    prices = _prices([100.0, 90.0, 95.0, 92.0])
    result = simulate_overlay(
        prices,
        [
            _initialize(prices),
            Signal(prices[0]["date"], prices[1]["date"], "OPEN", "tier_1", 0.8),
        ],
    )
    assert result["metrics"]["days_at_80"] == 3
    assert result["metrics"]["reset_count"] == 0
    assert result["metrics"]["trade_count"] == 2


def test_reset_occurs_only_on_session_after_recovery() -> None:
    prices = _prices([100.0, 90.0, 100.0, 101.0])
    result = simulate_overlay(
        prices,
        [
            _initialize(prices),
            Signal(prices[0]["date"], prices[1]["date"], "E1", "tier_1", 0.8),
            Signal(prices[2]["date"], prices[3]["date"], "E1", "reset", 0.7),
        ],
    )
    reset = result["trade_log"][-1]
    assert reset["signal_date"] == prices[2]["date"]
    assert reset["execution_date"] == prices[3]["date"]
    assert result["metrics"]["reset_count"] == 1


def test_each_tier_once_and_weight_cash_constraints() -> None:
    prices = _prices([100.0, 95.0, 90.0, 80.0, 85.0])
    signals = [
        _initialize(prices),
        Signal(prices[0]["date"], prices[1]["date"], "E1", "tier_1", 0.8),
        Signal(prices[1]["date"], prices[2]["date"], "E1", "tier_2", 0.9),
        Signal(prices[2]["date"], prices[3]["date"], "E1", "tier_3", 1.0),
    ]
    result = simulate_overlay(prices, signals)
    assert [result["metrics"][f"tier_{tier}_trigger_count"] for tier in (1, 2, 3)] == [1, 1, 1]
    assert result["metrics"]["maximum_asset_weight"] <= 1.0
    assert all(value > 0 for value in result["nav_values"])


def test_static_benchmarks_match_closed_form() -> None:
    prices = _prices([100.0, 110.0, 90.0])
    static = simulate_static_benchmark(prices, 0.7)
    buy_hold = simulate_static_benchmark(prices, 1.0)
    assert static["total_return"] == pytest.approx(-0.07)
    assert buy_hold["total_return"] == pytest.approx(-0.10)


def test_metric_formulas_cover_cagr_volatility_drawdown_and_calmar() -> None:
    nav = [1.0, 1.1, 0.88, 1.056]
    metrics = calculate_metrics(nav)
    returns = [0.1, -0.2, 0.2]
    expected_vol = math.sqrt(sum((r - sum(returns) / 3) ** 2 for r in returns) / 3) * math.sqrt(252)
    assert metrics["total_return"] == pytest.approx(0.056)
    assert metrics["cagr"] == pytest.approx(1.056 ** 84 - 1)
    assert metrics["annualized_volatility"] == pytest.approx(expected_vol)
    assert metrics["maximum_drawdown"] == pytest.approx(-0.2)
    assert metrics["calmar_ratio"] == pytest.approx(metrics["cagr"] / 0.2)


def test_formal_report_has_fixed_scope_delays_and_blocked_assets() -> None:
    report = build_drawdown_addon_candidate_backtest(
        ROOT, generated_at="2026-07-16T00:00:00+00:00"
    )
    assert report["report_type"] == "drawdown_addon_candidate_backtest"
    assert report["assumptions"]["tier_weights"] == [0.8, 0.9, 1.0]
    assert len(report["assets"]) == 5
    assert len(report["blocked_assets"]) == 2
    assert all("strategy" not in asset for asset in report["blocked_assets"])
    for asset in report["assets"]:
        log = asset["trade_log"]
        assert log[0]["action"] == "initialize"
        dates = json.loads(
            (ROOT / EVENT_DIRECTORY_RELATIVE / f"{asset['asset_key']}.json").read_text(encoding="utf-8")
        )["drawdown_series"]
        positions = {row["date"]: index for index, row in enumerate(dates)}
        for trade in log[1:]:
            assert (
                positions[trade["execution_date"]]
                == positions[trade["signal_date"]] + 1
            )
        event_tiers = [
            (trade["event_id"], trade["action"])
            for trade in log
            if trade["action"].startswith("tier_")
        ]
        assert len(event_tiers) == len(set(event_tiers))
        assert asset["strategy"]["trade_count"] == len(log)
        assert set(asset) == {
            "asset_key", "display_name", "risk_family", "period", "strategy",
            "benchmark_70_30", "benchmark_buy_hold", "comparison", "trade_log",
        }


def test_insufficient_history_does_not_trigger_and_terminal_signal_is_skipped() -> None:
    report = build_drawdown_addon_candidate_backtest(ROOT)
    for asset in report["assets"]:
        ledger = json.loads(
            (ROOT / LEDGER_DIRECTORY_RELATIVE / f"{asset['asset_key']}.json").read_text(encoding="utf-8")
        )
        insufficient_events = {
            event["event_id"]
            for event in ledger["event_evaluations"]
            if all(
                row["test_cohort"]["threshold_status"] == "insufficient_history"
                for row in event["threshold_evaluations"]
                if row["threshold_family"] == "completed_event_depth_quantile"
                and row["threshold_level"] in {"p75", "p90", "p95"}
            )
        }
        assert not any(
            trade["event_id"] in insufficient_events and trade["action"].startswith("tier_")
            for trade in asset["trade_log"]
        )


def test_signal_without_next_session_is_not_executed_in_formal_report() -> None:
    report = build_drawdown_addon_candidate_backtest(ROOT)
    for asset in report["assets"]:
        assert all(
            trade["signal_date"] != asset["period"]["last_date"]
            for trade in asset["trade_log"]
        )


def test_repeated_build_is_deterministic_except_generated_at_and_finite() -> None:
    first = build_drawdown_addon_candidate_backtest(
        ROOT, generated_at="2026-07-16T00:00:00+00:00"
    )
    second = build_drawdown_addon_candidate_backtest(
        ROOT, generated_at="2026-07-17T00:00:00+00:00"
    )
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second
    json.dumps(first, allow_nan=False)


def test_candidate_ledger_hash_mismatch_fails(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "reports", tmp_path / "reports")
    candidate_path = tmp_path / CANDIDATE_RELATIVE
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["source_ledger_index_sha256"] = "0" * 64
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    with pytest.raises(DrawdownAddonBacktestError, match="candidate ledger index hash differs"):
        build_drawdown_addon_candidate_backtest(tmp_path)
