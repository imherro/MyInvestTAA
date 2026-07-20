from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import statistics
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_RELATIVE = (
    "reports/strategy_research/drawdown_addon_trigger_candidate_v1.json"
)
LEDGER_DIRECTORY_RELATIVE = (
    "reports/strategy_research/drawdown_walk_forward_evidence"
)
EVENT_DIRECTORY_RELATIVE = "reports/strategy_research/drawdown_events"
OUTPUT_RELATIVE = (
    "reports/strategy_research/drawdown_addon_candidate_backtest_v1.json"
)
OUTPUT_REPORT_TYPE = "drawdown_addon_candidate_backtest"
ANALYZED_ASSETS = (
    "csi300_total_return",
    "csi500_total_return",
    "csi1000_total_return",
    "csi_dividend_total_return",
    "cni_free_cash_flow_total_return",
)
BLOCKED_ASSETS = ("chinext_total_return", "cni1000_value_total_return")
THRESHOLD_FAMILY = "completed_event_depth_quantile"
TIER_LEVELS = ((1, "p75", 0.8), (2, "p90", 0.9), (3, "p95", 1.0))
BASE_WEIGHT = 0.7
TRANSACTION_COST_RATE = 0.001
SESSIONS_PER_YEAR = 252
EPSILON = 1e-12


class DrawdownAddonBacktestError(ValueError):
    pass


@dataclass(frozen=True)
class Signal:
    signal_date: str
    execution_date: str
    event_id: str
    action: str
    target_weight: float


@dataclass
class PortfolioState:
    asset_units: float = 0.0
    cash_balance: float = 1.0
    target_weight: float = 0.0


def build_drawdown_addon_candidate_backtest(
    root: Path, *, generated_at: str | None = None
) -> dict[str, Any]:
    root = Path(root)
    candidate_bytes = (root / CANDIDATE_RELATIVE).read_bytes()
    ledger_directory = root / LEDGER_DIRECTORY_RELATIVE
    event_directory = root / EVENT_DIRECTORY_RELATIVE
    ledger_index_bytes = (ledger_directory / "index.json").read_bytes()
    event_index_bytes = (event_directory / "index.json").read_bytes()

    candidate = _load_json(candidate_bytes)
    ledger_index = _load_json(ledger_index_bytes)
    event_index = _load_json(event_index_bytes)
    _validate_inputs(
        candidate,
        ledger_index,
        event_index,
        ledger_directory,
        event_directory,
        ledger_index_bytes,
        event_index_bytes,
    )

    candidate_assets = {asset["asset_key"]: asset for asset in candidate["assets"]}
    ledger_entries = {asset["asset_key"]: asset for asset in ledger_index["assets"]}
    event_entries = {asset["asset_key"]: asset for asset in event_index["assets"]}
    results = []
    for asset_key in ANALYZED_ASSETS:
        ledger_report = _load_report(root, ledger_entries[asset_key]["report_path"])
        event_path = root / event_entries[asset_key]["report_path"]
        event_bytes = event_path.read_bytes()
        if hashlib.sha256(event_bytes).hexdigest() != ledger_entries[asset_key].get(
            "source_event_report_sha256"
        ):
            raise DrawdownAddonBacktestError(
                f"event report hash differs for {asset_key}"
            )
        event_report = _load_json(event_bytes)
        _validate_asset_reports(
            asset_key,
            candidate_assets[asset_key],
            ledger_entries[asset_key],
            event_entries[asset_key],
            ledger_report,
            event_report,
        )
        results.append(
            _backtest_asset(
                candidate_assets[asset_key], ledger_report, event_report
            )
        )

    blocked = []
    candidate_blocked = {
        asset["asset_key"]: asset for asset in candidate["blocked_assets"]
    }
    for asset_key in BLOCKED_ASSETS:
        ledger_report = _load_report(root, ledger_entries[asset_key]["report_path"])
        event_report = _load_report(root, event_entries[asset_key]["report_path"])
        expected = candidate_blocked[asset_key]
        if (
            ledger_report.get("analysis_status") != "blocked"
            or event_report.get("analysis_status") != "blocked"
            or ledger_entries[asset_key].get("blockers") != expected["blockers"]
            or event_entries[asset_key].get("blockers") != expected["blockers"]
            or ledger_report.get("blockers") != expected["blockers"]
            or event_report.get("blockers") != expected["blockers"]
        ):
            raise DrawdownAddonBacktestError(
                f"blocked asset identity differs for {asset_key}"
            )
        blocked.append(copy.deepcopy(expected))

    result = {
        "schema_version": "1.0",
        "report_type": OUTPUT_REPORT_TYPE,
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "source_candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "source_ledger_index_sha256": hashlib.sha256(
            ledger_index_bytes
        ).hexdigest(),
        "source_event_index_sha256": hashlib.sha256(event_index_bytes).hexdigest(),
        "assumptions": {
            "base_asset_weight": BASE_WEIGHT,
            "tier_weights": [weight for _, _, weight in TIER_LEVELS],
            "cash_annual_return": 0.0,
            "one_way_transaction_cost": TRANSACTION_COST_RATE,
            "execution_delay_sessions": 1,
            "initialization_cost_applies": True,
        },
        "assets": results,
        "blocked_assets": blocked,
    }
    _validate_result(result)
    _validate_finite(result)
    return result


def publish_drawdown_addon_candidate_backtest(
    target: Path, report: dict[str, Any]
) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=target.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(
            report,
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        handle.write("\n")
    try:
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def calculate_metrics(
    nav_values: list[float], *, initial_capital: float = 1.0
) -> dict[str, float]:
    if (
        not nav_values
        or initial_capital <= 0
        or any(value <= 0 for value in nav_values)
    ):
        raise DrawdownAddonBacktestError("NAV values must be positive")
    periods = max(len(nav_values) - 1, 1)
    total_return = nav_values[-1] / initial_capital - 1.0
    cagr = (nav_values[-1] / initial_capital) ** (
        SESSIONS_PER_YEAR / periods
    ) - 1.0
    daily_returns = [
        current / previous - 1.0
        for previous, current in zip(nav_values, nav_values[1:])
    ]
    volatility = (
        statistics.pstdev(daily_returns) * math.sqrt(SESSIONS_PER_YEAR)
        if daily_returns
        else 0.0
    )
    peak = initial_capital
    maximum_drawdown = 0.0
    for value in nav_values:
        peak = max(peak, value)
        maximum_drawdown = min(maximum_drawdown, value / peak - 1.0)
    calmar = cagr / abs(maximum_drawdown) if maximum_drawdown < 0 else 0.0
    return {
        "total_return": total_return,
        "cagr": cagr,
        "annualized_volatility": volatility,
        "maximum_drawdown": maximum_drawdown,
        "calmar_ratio": calmar,
    }


def simulate_overlay(
    prices: list[dict[str, Any]], signals: Iterable[Signal]
) -> dict[str, Any]:
    dates = [row["date"] for row in prices]
    closes = [float(row["close"]) for row in prices]
    if not dates or len(set(dates)) != len(dates) or dates != sorted(dates):
        raise DrawdownAddonBacktestError("price dates must be unique and increasing")
    if any(not math.isfinite(close) or close <= 0 for close in closes):
        raise DrawdownAddonBacktestError("price closes must be finite and positive")

    signal_map: dict[str, Signal] = {}
    for signal in signals:
        if signal.execution_date in signal_map:
            raise DrawdownAddonBacktestError("multiple executions on one date")
        signal_map[signal.execution_date] = signal

    state = PortfolioState()
    nav_values: list[float] = []
    trade_log: list[dict[str, Any]] = []
    maximum_asset_weight = 0.0
    days = {0.7: 0, 0.8: 0, 0.9: 0, 1.0: 0}
    total_cost = 0.0
    tier_counts = {1: 0, 2: 0, 3: 0}
    reset_count = 0

    for date, close in zip(dates, closes):
        pre_trade_nav = state.asset_units * close + state.cash_balance
        signal = signal_map.get(date)
        if signal is not None:
            current_weight = (
                state.asset_units * close / pre_trade_nav if pre_trade_nav else 0.0
            )
            cost = (
                pre_trade_nav
                * abs(signal.target_weight - current_weight)
                * TRANSACTION_COST_RATE
            )
            post_cost_nav = pre_trade_nav - cost
            old_target = state.target_weight
            state.asset_units = signal.target_weight * post_cost_nav / close
            state.cash_balance = (1.0 - signal.target_weight) * post_cost_nav
            state.target_weight = signal.target_weight
            total_cost += cost
            trade_log.append(
                {
                    "signal_date": signal.signal_date,
                    "execution_date": signal.execution_date,
                    "event_id": signal.event_id,
                    "action": signal.action,
                    "old_target_weight": old_target,
                    "new_target_weight": signal.target_weight,
                    "execution_close": close,
                    "transaction_cost": cost,
                }
            )
            if signal.action.startswith("tier_"):
                tier_counts[int(signal.action[-1])] += 1
            elif signal.action == "reset":
                reset_count += 1

        nav = state.asset_units * close + state.cash_balance
        if nav <= 0 or state.cash_balance < -EPSILON:
            raise DrawdownAddonBacktestError("portfolio state is invalid")
        actual_weight = state.asset_units * close / nav
        if not -EPSILON <= actual_weight <= 1.0 + EPSILON:
            raise DrawdownAddonBacktestError("asset weight is outside [0, 1]")
        maximum_asset_weight = max(maximum_asset_weight, actual_weight)
        if state.target_weight not in days:
            raise DrawdownAddonBacktestError("unexpected target weight")
        days[state.target_weight] += 1
        nav_values.append(nav)

    metrics = calculate_metrics(nav_values)
    metrics.update(
        {
            "tier_1_trigger_count": tier_counts[1],
            "tier_2_trigger_count": tier_counts[2],
            "tier_3_trigger_count": tier_counts[3],
            "reset_count": reset_count,
            "trade_count": len(trade_log),
            "total_transaction_cost": total_cost,
            "maximum_asset_weight": maximum_asset_weight,
            "days_at_70": days[0.7],
            "days_at_80": days[0.8],
            "days_at_90": days[0.9],
            "days_at_100": days[1.0],
        }
    )
    return {"metrics": metrics, "trade_log": trade_log, "nav_values": nav_values}


def simulate_static_benchmark(
    prices: list[dict[str, Any]], asset_weight: float
) -> dict[str, float]:
    closes = [float(row["close"]) for row in prices]
    first_close = closes[0]
    units = asset_weight / first_close
    cash = 1.0 - asset_weight
    return calculate_metrics([units * close + cash for close in closes])


def _backtest_asset(
    candidate_asset: dict[str, Any],
    ledger_report: dict[str, Any],
    event_report: dict[str, Any],
) -> dict[str, Any]:
    prices = event_report["drawdown_series"]
    dates = [row["date"] for row in prices]
    next_date = {date: dates[index + 1] for index, date in enumerate(dates[:-1])}
    event_by_id = {event["event_id"]: event for event in event_report["events"]}
    signals = [
        Signal(dates[0], dates[0], "INITIALIZATION", "initialize", BASE_WEIGHT)
    ]
    reached_tiers: dict[str, set[int]] = {}

    for evaluation in ledger_report["event_evaluations"]:
        event_id = evaluation["event_id"]
        if event_id not in event_by_id:
            raise DrawdownAddonBacktestError(f"missing event {event_id}")
        grouped: dict[str, list[tuple[int, float]]] = {}
        for threshold in evaluation["threshold_evaluations"]:
            tier = _candidate_tier(threshold)
            if tier is None:
                continue
            status = threshold["test_cohort"]["threshold_status"]
            trigger_date = threshold["test_cohort"].get("trigger_date")
            if status == "reached":
                if trigger_date not in next_date:
                    continue
                grouped.setdefault(trigger_date, []).append((tier[0], tier[2]))
            elif status in {"not_reached", "insufficient_history"}:
                if trigger_date is not None:
                    raise DrawdownAddonBacktestError(
                        "disabled tier cannot have a trigger date"
                    )
            else:
                raise DrawdownAddonBacktestError(f"invalid threshold status {status}")

        previous_tier = 0
        reached_tiers[event_id] = set()
        for signal_date in sorted(grouped):
            tier_number, target_weight = max(grouped[signal_date])
            if tier_number <= previous_tier:
                continue
            for reached_tier in range(previous_tier + 1, tier_number + 1):
                reached_tiers[event_id].add(reached_tier)
            previous_tier = tier_number
            signals.append(
                Signal(
                    signal_date,
                    next_date[signal_date],
                    event_id,
                    f"tier_{tier_number}",
                    target_weight,
                )
            )

        recovery_date = event_by_id[event_id].get("recovery_date")
        if recovery_date is not None:
            if recovery_date not in dates:
                raise DrawdownAddonBacktestError("recovery date is absent from prices")
            if recovery_date in next_date and previous_tier > 0:
                signals.append(
                    Signal(
                        recovery_date,
                        next_date[recovery_date],
                        event_id,
                        "reset",
                        BASE_WEIGHT,
                    )
                )

    signals.sort(key=lambda signal: (signal.execution_date, signal.action))
    _validate_signal_sequence(signals, reached_tiers)
    overlay = simulate_overlay(prices, signals)
    static = simulate_static_benchmark(prices, BASE_WEIGHT)
    buy_hold = simulate_static_benchmark(prices, 1.0)
    metrics = overlay["metrics"]
    comparison = {
        "excess_total_return_vs_70_30": metrics["total_return"]
        - static["total_return"],
        "excess_cagr_vs_70_30": metrics["cagr"] - static["cagr"],
        "maximum_drawdown_difference_vs_70_30": metrics["maximum_drawdown"]
        - static["maximum_drawdown"],
        "excess_total_return_vs_buy_hold": metrics["total_return"]
        - buy_hold["total_return"],
        "maximum_drawdown_difference_vs_buy_hold": metrics["maximum_drawdown"]
        - buy_hold["maximum_drawdown"],
    }
    return {
        "asset_key": candidate_asset["asset_key"],
        "display_name": candidate_asset["display_name"],
        "risk_family": candidate_asset["risk_family"],
        "period": {
            "first_date": prices[0]["date"],
            "last_date": prices[-1]["date"],
            "session_count": len(prices),
        },
        "strategy": metrics,
        "benchmark_70_30": static,
        "benchmark_buy_hold": buy_hold,
        "comparison": comparison,
        "trade_log": overlay["trade_log"],
    }


def _candidate_tier(threshold: dict[str, Any]) -> tuple[int, str, float] | None:
    if threshold.get("threshold_family") != THRESHOLD_FAMILY:
        return None
    level = threshold.get("threshold_level")
    matches = [tier for tier in TIER_LEVELS if tier[1] == level]
    return matches[0] if matches else None


def _validate_signal_sequence(
    signals: list[Signal], reached_tiers: dict[str, set[int]]
) -> None:
    seen: dict[str, set[int]] = {event_id: set() for event_id in reached_tiers}
    target = 0.0
    for signal in signals:
        if signal.action == "initialize":
            if target != 0.0 or signal.target_weight != BASE_WEIGHT:
                raise DrawdownAddonBacktestError("initialization must be first")
        elif signal.action.startswith("tier_"):
            tier = int(signal.action[-1])
            if tier in seen[signal.event_id]:
                raise DrawdownAddonBacktestError("tier triggered more than once")
            seen[signal.event_id].add(tier)
            if signal.target_weight <= target:
                raise DrawdownAddonBacktestError("tier cannot reduce target weight")
        elif signal.action == "reset":
            if signal.target_weight != BASE_WEIGHT:
                raise DrawdownAddonBacktestError("reset target is invalid")
        else:
            raise DrawdownAddonBacktestError("unknown action")
        target = signal.target_weight


def _validate_inputs(
    candidate: dict[str, Any],
    ledger_index: dict[str, Any],
    event_index: dict[str, Any],
    ledger_directory: Path,
    event_directory: Path,
    ledger_index_bytes: bytes,
    event_index_bytes: bytes,
) -> None:
    if candidate.get("report_type") != "a_tier_drawdown_addon_trigger_candidate":
        raise DrawdownAddonBacktestError("candidate report type is invalid")
    rule = candidate.get("rule", {})
    if rule.get("threshold_family") != THRESHOLD_FAMILY or rule.get("tiers") != [
        {"tier": tier, "threshold_level": level}
        for tier, level, _ in TIER_LEVELS
    ]:
        raise DrawdownAddonBacktestError("candidate tiers are not pre-registered")
    expected_flags = {
        "thresholds_computed_at_event_peak": True,
        "thresholds_frozen_within_event": True,
        "trigger_on_first_reach_or_exceed": True,
        "trigger_once_per_event": True,
        "deeper_tier_preserves_shallower_tiers": True,
        "reset_on_peak_recovery": True,
        "insufficient_history_disables_tier": True,
    }
    if any(rule.get(key) is not value for key, value in expected_flags.items()):
        raise DrawdownAddonBacktestError("candidate rule flags are invalid")
    expected_tiers = [
        (tier, THRESHOLD_FAMILY, level)
        for tier, level, _ in TIER_LEVELS
    ]
    for asset in candidate.get("assets", []):
        actual_tiers = [
            (
                tier.get("tier"),
                tier.get("threshold_family"),
                tier.get("threshold_level"),
            )
            for tier in asset.get("tiers", [])
        ]
        if actual_tiers != expected_tiers:
            raise DrawdownAddonBacktestError("candidate asset tiers differ")
    if candidate.get("source_ledger_index_sha256") != hashlib.sha256(
        ledger_index_bytes
    ).hexdigest():
        raise DrawdownAddonBacktestError("candidate ledger index hash differs")
    if ledger_index.get("source_event_index_sha256") != hashlib.sha256(
        event_index_bytes
    ).hexdigest():
        raise DrawdownAddonBacktestError("ledger event index hash differs")
    if ledger_index.get("report_type") != "a_tier_drawdown_walk_forward_evidence_index":
        raise DrawdownAddonBacktestError("ledger index type is invalid")
    if event_index.get("report_type") != "a_tier_drawdown_event_index":
        raise DrawdownAddonBacktestError("event index type is invalid")
    for directory in (ledger_directory, event_directory):
        if len(list(directory.glob("*.json"))) != 8:
            raise DrawdownAddonBacktestError(
                f"{directory.name} must contain exactly eight JSON files"
            )
    expected_assets = set(ANALYZED_ASSETS + BLOCKED_ASSETS)
    for source in (candidate, ledger_index, event_index):
        keys = {asset["asset_key"] for asset in source["assets"]}
        if source is candidate:
            keys |= {asset["asset_key"] for asset in source["blocked_assets"]}
        if keys != expected_assets:
            raise DrawdownAddonBacktestError("asset universe differs")


def _validate_asset_reports(
    asset_key: str,
    candidate_asset: dict[str, Any],
    ledger_entry: dict[str, Any],
    event_entry: dict[str, Any],
    ledger_report: dict[str, Any],
    event_report: dict[str, Any],
) -> None:
    identities = (candidate_asset, ledger_entry, event_entry, ledger_report, event_report)
    if any(
        item.get("asset_key", item.get("asset", {}).get("asset_key")) != asset_key
        for item in identities
    ):
        raise DrawdownAddonBacktestError(f"asset identity differs for {asset_key}")
    if any(item.get("analysis_status", "analyzed") != "analyzed" for item in identities):
        raise DrawdownAddonBacktestError(f"asset is not analyzed: {asset_key}")
    if ledger_report.get("source_event_report_sha256") != ledger_entry.get(
        "source_event_report_sha256"
    ):
        raise DrawdownAddonBacktestError("ledger event source hash differs")
    event_ids = [event["event_id"] for event in event_report.get("events", [])]
    ledger_ids = [event["event_id"] for event in ledger_report.get("event_evaluations", [])]
    if event_ids != ledger_ids or not event_ids:
        raise DrawdownAddonBacktestError("ledger/event identities differ")
    price_dates = {row["date"] for row in event_report.get("drawdown_series", [])}
    for event in event_report["events"]:
        if event["peak_date"] not in price_dates:
            raise DrawdownAddonBacktestError("peak date is absent from prices")
        if event.get("recovery_date") is not None and event["recovery_date"] not in price_dates:
            raise DrawdownAddonBacktestError("recovery date is absent from prices")
    for evaluation in ledger_report["event_evaluations"]:
        for threshold in evaluation["threshold_evaluations"]:
            if _candidate_tier(threshold) is not None:
                trigger = threshold["test_cohort"].get("trigger_date")
                if trigger is not None and trigger not in price_dates:
                    raise DrawdownAddonBacktestError("trigger date is absent from prices")


def _validate_result(result: dict[str, Any]) -> None:
    if len(result["assets"]) != 5 or len(result["blocked_assets"]) != 2:
        raise DrawdownAddonBacktestError("result asset counts are invalid")
    if [asset["asset_key"] for asset in result["assets"]] != list(ANALYZED_ASSETS):
        raise DrawdownAddonBacktestError("analyzed result order differs")
    for asset in result["assets"]:
        strategy = asset["strategy"]
        day_count = sum(
            strategy[key]
            for key in ("days_at_70", "days_at_80", "days_at_90", "days_at_100")
        )
        if day_count != asset["period"]["session_count"]:
            raise DrawdownAddonBacktestError("target-weight day counts differ")
        if strategy["trade_count"] != len(asset["trade_log"]):
            raise DrawdownAddonBacktestError("trade count differs")
        if not 0 <= strategy["maximum_asset_weight"] <= 1 + EPSILON:
            raise DrawdownAddonBacktestError("maximum asset weight is invalid")
    if any("strategy" in asset or "trade_log" in asset for asset in result["blocked_assets"]):
        raise DrawdownAddonBacktestError("blocked asset contains a backtest")


def _validate_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise DrawdownAddonBacktestError("output contains a non-finite number")
    if isinstance(value, dict):
        for nested in value.values():
            _validate_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _validate_finite(nested)


def _load_report(root: Path, relative_path: str) -> dict[str, Any]:
    return _load_json((root / relative_path).read_bytes())


def _load_json(content: bytes) -> dict[str, Any]:
    value = json.loads(content.decode("utf-8"))
    if not isinstance(value, dict):
        raise DrawdownAddonBacktestError("JSON root must be an object")
    return value


def main() -> int:
    report = build_drawdown_addon_candidate_backtest(ROOT)
    target = ROOT / OUTPUT_RELATIVE
    publish_drawdown_addon_candidate_backtest(target, report)
    print(target.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
