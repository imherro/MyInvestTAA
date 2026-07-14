from __future__ import annotations

import hashlib
import json
from statistics import median

from backtest.execution.mapping import build_execution_mapping
from backtest.execution.v2.calendar import next_trade_date
from backtest.execution.v2.investability import build_investability_timeline, investability_state
from backtest.execution.v2.models import ExecutionV2Config
from backtest.research.metrics import build_metrics
from engine.asset_registry.loader import ROOT


GAP_KEYS = (
    "no_approved_proxy_cash",
    "low_quality_proxy_cash",
    "not_yet_investable_cash",
    "missing_entry_price_cash",
    "metadata_unverified_cash",
)


def run_execution_backtest_v2(research_report, execution_price_data, mappings, execution_universe, calendar, metadata, *, v1_report, config=None, data_provider="unknown"):
    cfg = config or ExecutionV2Config()
    research_period = research_report["period"]
    dates = [date for date in calendar["dates"] if research_period["start"] <= date <= research_period["end"]]
    if len(dates) < 2:
        return {"available": False, "message": "insufficient local trade calendar coverage"}, {}, {}
    allocations = research_report.get("monthly_allocations", [])
    mapping_rows = build_execution_mapping(allocations, mappings, execution_universe)
    mapping_by_research = {row["research_asset_id"]: row for row in mapping_rows}
    price_maps = {asset_id: {row.date: row.close for row in rows} for asset_id, rows in execution_price_data.items()}
    timeline_rows = build_investability_timeline(dates, metadata, price_maps)
    schedules = {}
    for allocation in allocations:
        scheduled = next_trade_date(dates, allocation["date"])
        if scheduled:
            schedules.setdefault(scheduled, []).append(allocation)

    positions = {}
    last_prices = {}
    cash = 1.0
    curve = []
    daily_states = []
    execution_events = []
    stale_valuation_days = 0
    first_holding_date = None
    for date in dates:
        stale = []
        for asset_id, value in list(positions.items()):
            current_price = price_maps.get(asset_id, {}).get(date)
            previous_price = last_prices.get(asset_id)
            if current_price is not None and previous_price and previous_price > 0:
                positions[asset_id] = value * current_price / previous_price
                last_prices[asset_id] = current_price
            elif current_price is not None:
                last_prices[asset_id] = current_price
            else:
                stale.append(asset_id)
        if stale:
            stale_valuation_days += 1
        nav = cash + sum(positions.values())
        day_events = []
        for allocation in schedules.get(date, []):
            translated = _translate(allocation, date, mapping_by_research, metadata, price_maps)
            positions, cash, event = _rebalance(nav, positions, cash, last_prices, price_maps, date, translated, allocation)
            nav = cash + sum(positions.values())
            execution_events.append(event)
            day_events.append(event)
        if positions and first_holding_date is None:
            first_holding_date = date
        weights = {asset_id: round(value / nav, 10) for asset_id, value in sorted(positions.items())} if nav else {}
        weights["CASH"] = round(cash / nav, 10) if nav else 0.0
        curve.append({"date": date, "value": round(nav, 8)})
        daily_states.append({"date": date, "nav": round(nav, 8), "weights": weights, "stale_valuation_assets": stale, "execution_events": day_events})

    metrics = build_metrics(curve)
    gap_contract = _gap_contract(execution_events)
    periods = {
        "research_full_period": research_period,
        "simulation_calendar_period": {"start": dates[0], "end": dates[-1]},
        "first_etf_investable_date": min(row["investable_start_date"] for row in metadata.values()),
        "first_etf_investable_date_in_simulation": max(
            dates[0], min(row["investable_start_date"] for row in metadata.values())
        ),
        "first_actual_etf_holding_date": first_holding_date,
        "fully_observed_period": {"start": dates[0], "end": dates[-1]},
        "common_v1_comparison_period": {"start": max(dates[0], v1_report["period"]["start"]), "end": min(dates[-1], v1_report["period"]["end"])},
    }
    comparison = _comparison(v1_report, curve, periods["common_v1_comparison_period"])
    source_manifest = _source_manifest()
    report = {
        "available": True,
        "strategy": cfg.strategy,
        "engine_status": cfg.engine_status,
        "eligible_to_replace_v1": False,
        "production_actionable": False,
        "data_provider": data_provider,
        "periods": periods,
        "calendar_contract": {"source": calendar.get("source"), "verified": calendar.get("verified"), "global_etf_date_intersection_used": False, "trade_day_count": len(dates)},
        "execution_timing_contract": {"signal_known": "signal_date_close", "earliest_execution": "next_trade_day_close", "new_weights_effective": "next_return_interval", "same_day_lookahead_allowed": False},
        "price_availability_contract": {"held_missing_price": "last_verified_price_zero_daily_return_no_trade", "unheld_missing_price": "cannot_enter_route_to_cash", "index_return_substitution_allowed": False, "pre_listing_etf_return_allowed": False},
        "cost_policy": {"commission_bps": cfg.commission_bps, "slippage_bps": cfg.slippage_bps, "transaction_cost": 0.0, "mode": "B1_zero_cost"},
        "cash_yield_policy": {"cash_yield": cfg.cash_yield, "mode": "B1_zero_cash_yield"},
        "metrics_gross": metrics,
        "metrics_net": metrics,
        "equity_curve_gross": curve,
        "equity_curve_net": curve,
        "monthly_allocations": execution_events,
        "daily_portfolio_states": daily_states,
        "investability_summary": _timeline_summary(timeline_rows, stale_valuation_days),
        "coverage_contract": gap_contract["coverage_contract"],
        "gap_metrics": gap_contract["gap_metrics"],
        "transaction_cost_attribution": {"total_transaction_cost": 0.0, "cumulative_cost_drag": 0.0},
        "cash_yield_attribution": {"cash_interest_contribution": 0.0, "cash_yield_available": False},
        "unavailable_weight_attribution": gap_contract["reason_average_weights"],
        "mapping_summary_schema_version": "2.0",
        "warnings": ["Experimental validation only; V1 remains formal.", "Listing date is used as B1 investable start and does not prove liquidity readiness.", "No orders, shares, quantities, amounts, or target prices are produced."],
        "source_manifest": source_manifest,
        "validation": {"deterministic_inputs": True, "weights_reconcile": all(abs(sum(row["weights"].values()) - 1) < 1e-6 for row in daily_states), "pre_listing_return_used": False, "index_return_substitution_used": False},
        "comparison_to_v1": comparison,
    }
    timeline = {"available": True, "strategy": cfg.strategy, "period": periods["simulation_calendar_period"], "rows": timeline_rows, "source_manifest": source_manifest}
    return report, timeline, comparison


def _translate(allocation, date, mapping_by_research, metadata, price_maps):
    targets = {}
    cash_breakdown = {"research_cash": float(allocation.get("weights", {}).get("CASH", 0)), **{key: 0.0 for key in GAP_KEYS}}
    details = []
    for research_id, raw_weight in allocation.get("weights", {}).items():
        if research_id == "CASH":
            continue
        weight = float(raw_weight)
        row = mapping_by_research.get(research_id)
        quality = row.get("mapping_quality") if row else "none"
        proxy = row.get("proxy_id") if row else None
        if quality == "low":
            bucket, reason = "low_quality_proxy_cash", "low_quality_excluded"
        elif not proxy:
            bucket, reason = "no_approved_proxy_cash", "no_approved_proxy"
        elif proxy not in metadata or not metadata[proxy].get("verified"):
            bucket, reason = "metadata_unverified_cash", "metadata_unverified"
        else:
            state = investability_state(date, metadata[proxy], price_maps.get(proxy, {}))
            if state["state"] in {"before_listing", "before_investable_start"}:
                bucket, reason = "not_yet_investable_cash", state["state"]
            elif not state["can_enter"]:
                bucket, reason = "missing_entry_price_cash", state["state"]
            else:
                targets[proxy] = targets.get(proxy, 0.0) + weight
                details.append({"research_asset_id": research_id, "weight": weight, "destination": proxy, "reason": "executable", "mapping_quality": quality})
                continue
        cash_breakdown[bucket] += weight
        details.append({"research_asset_id": research_id, "weight": weight, "destination": "CASH", "reason": reason, "mapping_quality": quality})
    return {"targets": targets, "cash_breakdown": cash_breakdown, "details": details}


def _rebalance(nav, positions, cash, last_prices, price_maps, date, translated, allocation):
    frozen = {asset_id: value for asset_id, value in positions.items() if date not in price_maps.get(asset_id, {})}
    target_values = {asset_id: nav * weight for asset_id, weight in translated["targets"].items() if date in price_maps.get(asset_id, {})}
    available_value = max(nav - sum(frozen.values()), 0.0)
    desired = sum(target_values.values())
    if desired > available_value and desired > 0:
        scale = available_value / desired
        target_values = {key: value * scale for key, value in target_values.items()}
    new_positions = {**frozen, **target_values}
    for asset_id in target_values:
        last_prices[asset_id] = price_maps[asset_id][date]
    new_cash = nav - sum(new_positions.values())
    post_weights = {asset_id: round(value / nav, 10) for asset_id, value in sorted(new_positions.items())}
    post_weights["CASH"] = round(new_cash / nav, 10)
    event = {
        "signal_date": allocation["date"],
        "scheduled_execution_date": date,
        "actual_execution_date": date,
        "deferred_days": 0,
        "deferred_reason": "held_asset_missing_price" if frozen else None,
        "weights": post_weights,
        "cash_breakdown": {key: round(value, 10) for key, value in translated["cash_breakdown"].items()},
        "translation_details": translated["details"],
        "transaction_cost": 0.0,
    }
    return new_positions, new_cash, event


def _gap_contract(events):
    count = len(events)
    tradable = sum(sum(value for key, value in row["weights"].items() if key != "CASH") for row in events)
    non_cash = sum(1 - row["cash_breakdown"]["research_cash"] for row in events)
    total = float(count)
    gaps = [sum(row["cash_breakdown"].get(key, 0) for key in GAP_KEYS) for row in events]
    reason_average = {key: round(sum(row["cash_breakdown"].get(key, 0) for row in events) / count, 6) if count else 0.0 for key in GAP_KEYS}
    return {
        "coverage_contract": {"schema_version": "2.0", "metrics": [
            {"metric": "tradable_weight_coverage", "numerator": "tradable_translated_weight", "denominator": "non_cash_research_weight", "numerator_weight_period_sum": round(tradable, 10), "denominator_weight_period_sum": round(non_cash, 10), "formula": "tradable_translated_weight / non_cash_research_weight", "unit": "fraction", "value": round(tradable / non_cash, 6) if non_cash else 0.0},
            {"metric": "tradable_weight_coverage_total_portfolio", "numerator": "tradable_translated_weight", "denominator": "total_research_portfolio_weight", "numerator_weight_period_sum": round(tradable, 10), "denominator_weight_period_sum": round(total, 10), "formula": "tradable_translated_weight / total_research_portfolio_weight", "unit": "fraction", "value": round(tradable / total, 6) if total else 0.0},
        ]},
        "gap_metrics": {"binary_any_gap_month_ratio": round(sum(value > 1e-10 for value in gaps) / count, 6) if count else 0.0, "average_gap_weight": round(sum(gaps) / count, 6) if count else 0.0, "median_gap_weight": round(median(gaps), 6) if gaps else 0.0, "max_gap_weight": round(max(gaps), 6) if gaps else 0.0},
        "reason_average_weights": reason_average,
    }


def _timeline_summary(rows, stale_valuation_days):
    counts = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    return {"state_counts": counts, "timeline_row_count": len(rows), "stale_valuation_days": stale_valuation_days}


def _comparison(v1, v2_curve, period):
    v1_curve = _normalize([row for row in v1.get("equity_curve", []) if period["start"] <= row["date"] <= period["end"]])
    v2_common = _normalize([row for row in v2_curve if period["start"] <= row["date"] <= period["end"]])
    v1_dates = {row["date"] for row in v1.get("equity_curve", [])}
    v2_dates = {row["date"] for row in v2_curve}
    return {
        "available": True,
        "status": "neutral_attribution_only",
        "interpretation": "Metric differences are descriptive and do not establish V2 superiority.",
        "v1_period": v1.get("period"),
        "v2_simulation_period": {"start": v2_curve[0]["date"], "end": v2_curve[-1]["date"]},
        "common_comparison_period": period,
        "v1_common_metrics": build_metrics(v1_curve),
        "v2_common_metrics": build_metrics(v2_common),
        "calendar_attribution": {
            "days_retained_that_v1_deleted": len(v2_dates - v1_dates),
            "period_extension_days": sum(row["date"] < v1["period"]["start"] for row in v2_curve),
        },
        "b1_policy_attribution": {
            "transaction_cost": 0.0,
            "slippage": 0.0,
            "cash_yield": 0.0,
            "late_etf_policy": "route unavailable target weight to not_yet_investable_cash",
            "missing_price_policy": "retain calendar; freeze held valuation; block unheld entry",
        },
        "days_retained_that_v1_deleted": len(v2_dates - v1_dates),
        "period_extension_days": sum(row["date"] < v1["period"]["start"] for row in v2_curve),
        "v1_report_sha256": _sha(ROOT / "reports" / "execution_backtest_report.json"),
        "eligible_to_replace_v1": False,
    }


def _normalize(rows):
    if not rows:
        return []
    base = rows[0]["value"]
    return [{"date": row["date"], "value": row["value"] / base} for row in rows]


def _source_manifest():
    paths = [
        "reports/research_backtest_report.json", "reports/execution_backtest_report.json", "reports/execution_price_dataset_manifest.json",
        "data/universe/asset_mapping.json", "data/universe/execution_mapping_decision_ledger.json", "data/universe/execution_instrument_metadata.json",
        "data/market/cn_equity_trade_calendar.json", "backtest/execution/v2/engine.py", "backtest/execution/v2/investability.py", "backtest/execution/v2/calendar.py",
    ]
    manifest = {path: {"sha256": _sha(ROOT / path)} for path in paths}
    price_manifest = json.loads((ROOT / "reports" / "execution_price_dataset_manifest.json").read_text(encoding="utf-8"))
    for instrument_id, details in price_manifest.get("files", {}).items():
        path = f"data/execution_prices/{instrument_id.replace('.', '_')}.json"
        manifest[path] = {
            "sha256": _sha(ROOT / path),
            "declared_sha256": details.get("sha256"),
            "declared_hash_matches": _sha(ROOT / path) == details.get("sha256"),
        }
    return manifest


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
