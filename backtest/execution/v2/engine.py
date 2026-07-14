from __future__ import annotations

from datetime import date as Date
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


def run_execution_backtest_v2(
    research_report,
    execution_price_data,
    mappings,
    execution_universe,
    calendar,
    metadata,
    *,
    v1_report,
    config=None,
    data_provider="unknown",
):
    cfg = config or ExecutionV2Config()
    research_period = research_report["period"]
    dates = [value for value in calendar["dates"] if research_period["start"] <= value <= research_period["end"]]
    if len(dates) < 2:
        return {"available": False, "message": "insufficient local trade calendar coverage"}, {}, {}

    allocations = research_report.get("monthly_allocations", [])
    mapping_rows = build_execution_mapping(allocations, mappings, execution_universe)
    mapping_by_research = {row["research_asset_id"]: row for row in mapping_rows}
    price_maps = {
        asset_id: {row.date: row.close for row in rows}
        for asset_id, rows in execution_price_data.items()
    }
    _validate_price_metadata_contract(price_maps, metadata)
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
    signal_events = []
    pending_records = []
    stale_periods = []
    first_holding_date = None

    for current_date in dates:
        stale = _mark_to_market(current_date, positions, last_prices, price_maps)
        nav = cash + sum(positions.values())
        cash, pending_attempts = _process_pending(
            current_date,
            dates,
            nav,
            positions,
            cash,
            last_prices,
            price_maps,
            pending_records,
            signal_events,
        )
        nav = cash + sum(positions.values())
        day_events = list(pending_attempts)
        for allocation in schedules.get(current_date, []):
            translated = _translate(
                allocation, current_date, mapping_by_research, metadata, price_maps, positions
            )
            cash, event = _rebalance(
                nav,
                positions,
                cash,
                last_prices,
                price_maps,
                current_date,
                translated,
                allocation,
                pending_records,
                signal_events,
            )
            nav = cash + sum(positions.values())
            signal_events.append(event)
            day_events.append(event)
        if positions and first_holding_date is None:
            first_holding_date = current_date
        weights = _weights(positions, cash, nav)
        if stale:
            stale_periods.append({"date": current_date, "instrument_ids": sorted(stale)})
        curve.append({"date": current_date, "value": round(nav, 8)})
        daily_states.append(
            {
                "date": current_date,
                "nav": round(nav, 8),
                "weights": weights,
                "stale_valuation_assets": sorted(stale),
                "pending_adjustment_ids": [
                    row["adjustment_id"] for row in pending_records if row["status"] == "pending"
                ],
                "execution_events": day_events,
            }
        )

    metrics = build_metrics(curve)
    gap_contract = _gap_contract(signal_events)
    shared_period = {
        "start": max(dates[0], v1_report["period"]["start"]),
        "end": min(dates[-1], v1_report["period"]["end"]),
    }
    periods = {
        "research_full_period": research_period,
        "master_calendar_period": {"start": dates[0], "end": dates[-1]},
        "portfolio_valuation_period": {"start": dates[0], "end": dates[-1]},
        "first_etf_investable_date": min(row["investable_start_date"] for row in metadata.values()),
        "first_etf_investable_date_in_simulation": max(
            dates[0], min(row["investable_start_date"] for row in metadata.values())
        ),
        "first_actual_etf_holding_date": first_holding_date,
        "fresh_price_complete_period": {
            "available": False,
            "reason": "registered instruments contain listing or price-availability gaps",
        },
        "stale_valuation_periods": stale_periods,
        "common_exact_date_period": shared_period,
        "common_v1_comparison_period": shared_period,
    }
    comparison = _comparison(v1_report, curve, shared_period, signal_events, timeline_rows, stale_periods)
    source_manifest = _source_manifest()
    report = {
        "available": True,
        "strategy": cfg.strategy,
        "engine_status": cfg.engine_status,
        "eligible_to_replace_v1": False,
        "production_actionable": False,
        "data_provider": data_provider,
        "generated_at": calendar.get("generated_at"),
        "periods": periods,
        "calendar_contract": {
            "source": calendar.get("source"),
            "verified": calendar.get("verified"),
            "global_etf_date_intersection_used": False,
            "trade_day_count": len(dates),
        },
        "execution_timing_contract": {
            "signal_known": "signal_date_close",
            "earliest_execution": "next_trade_day_close",
            "new_weights_effective": "next_return_interval",
            "same_day_lookahead_allowed": False,
            "daily_order": "mark_to_market_then_pending_then_new_signal",
        },
        "price_availability_contract": {
            "held_missing_price": "last_verified_price_zero_daily_return_no_trade_pending_adjustment",
            "unheld_missing_price": "cannot_enter_route_to_cash_no_auto_retry",
            "index_return_substitution_allowed": False,
            "pre_listing_etf_return_allowed": False,
        },
        "cost_policy": {
            "commission_bps": cfg.commission_bps,
            "slippage_bps": cfg.slippage_bps,
            "transaction_cost": 0.0,
            "mode": "B1_zero_cost",
        },
        "cash_yield_policy": {"cash_yield": cfg.cash_yield, "mode": "B1_zero_cash_yield"},
        "metrics_gross": {**metrics, "dated": _dated_metrics(curve)},
        "metrics_net": {**metrics, "dated": _dated_metrics(curve)},
        "equity_curve_gross": curve,
        "equity_curve_net": curve,
        "monthly_allocations": signal_events,
        "pending_adjustments": pending_records,
        "daily_portfolio_states": daily_states,
        "investability_summary": _timeline_summary(timeline_rows, len(stale_periods)),
        "coverage_contract": gap_contract["coverage_contract"],
        "gap_metrics": gap_contract["gap_metrics"],
        "transaction_cost_attribution": {"total_transaction_cost": 0.0, "cumulative_cost_drag": 0.0},
        "cash_yield_attribution": {"cash_interest_contribution": 0.0, "cash_yield_available": False},
        "unavailable_weight_attribution": gap_contract["reason_average_weights"],
        "deferred_weight_attribution": _deferred_summary(pending_records),
        "mapping_summary_schema_version": "2.0",
        "warnings": [
            "Experimental validation only; V1 remains formal.",
            "Listing date is used as B1 investable start and does not prove liquidity readiness.",
            "No orders, shares, quantities, amounts, or target prices are produced.",
        ],
        "source_manifest": source_manifest,
        "validation": {
            "deterministic_inputs": True,
            "weights_reconcile": all(abs(sum(row["weights"].values()) - 1) < 1e-6 for row in daily_states),
            "pre_listing_return_used": False,
            "index_return_substitution_used": False,
            "event_reconciliation_verified": all(
                event["reconciliation"]["verified"] for event in signal_events
            ),
        },
        "comparison_to_v1": comparison,
    }
    timeline = {
        "available": True,
        "strategy": cfg.strategy,
        "period": periods["master_calendar_period"],
        "rows": timeline_rows,
        "source_manifest": source_manifest,
    }
    return report, timeline, comparison


def _mark_to_market(current_date, positions, last_prices, price_maps):
    stale = []
    for asset_id, value in list(positions.items()):
        current_price = price_maps.get(asset_id, {}).get(current_date)
        previous_price = last_prices.get(asset_id)
        if current_price is not None and previous_price and previous_price > 0:
            positions[asset_id] = value * current_price / previous_price
            last_prices[asset_id] = current_price
        elif current_price is not None:
            last_prices[asset_id] = current_price
        else:
            stale.append(asset_id)
    return stale


def _translate(allocation, current_date, mapping_by_research, metadata, price_maps, positions):
    targets = {}
    cash_breakdown = {
        "research_cash": float(allocation.get("weights", {}).get("CASH", 0)),
        **{key: 0.0 for key in GAP_KEYS},
    }
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
            state = investability_state(current_date, metadata[proxy], price_maps.get(proxy, {}))
            if state["state"] in {"before_listing", "before_investable_start"}:
                bucket, reason = "not_yet_investable_cash", state["state"]
            elif not state["can_enter"] and proxy not in positions:
                bucket, reason = "missing_entry_price_cash", state["state"]
            else:
                targets[proxy] = targets.get(proxy, 0.0) + weight
                details.append(
                    {
                        "research_asset_id": research_id,
                        "weight": weight,
                        "destination": proxy,
                        "reason": "held_missing_price_deferred" if not state["can_enter"] else "executable",
                        "mapping_quality": quality,
                    }
                )
                continue
        cash_breakdown[bucket] += weight
        details.append(
            {
                "research_asset_id": research_id,
                "weight": weight,
                "destination": "CASH",
                "reason": reason,
                "mapping_quality": quality,
            }
        )
    return {"targets": targets, "cash_breakdown": cash_breakdown, "details": details}


def _rebalance(
    nav,
    positions,
    cash,
    last_prices,
    price_maps,
    current_date,
    translated,
    allocation,
    pending_records,
    signal_events,
):
    event_id = f"signal-{allocation['date']}"
    _supersede_pending(current_date, allocation["date"], pending_records, signal_events)
    requested_targets = dict(translated["targets"])
    all_assets = set(positions) | set(requested_targets)
    frozen = {asset_id for asset_id in positions if current_date not in price_maps.get(asset_id, {})}
    executable_targets = {
        asset_id: weight
        for asset_id, weight in requested_targets.items()
        if asset_id not in frozen and current_date in price_maps.get(asset_id, {})
    }
    for asset_id in sorted(all_assets - frozen):
        target_value = nav * requested_targets.get(asset_id, 0.0)
        if target_value > 0:
            positions[asset_id] = target_value
            last_prices[asset_id] = price_maps[asset_id][current_date]
        else:
            positions.pop(asset_id, None)
            last_prices.pop(asset_id, None)

    deferred = []
    for asset_id in sorted(frozen):
        current_weight = positions[asset_id] / nav if nav else 0.0
        target_weight = requested_targets.get(asset_id, 0.0)
        if abs(target_weight - current_weight) > 1e-10:
            record = _pending_record(
                event_id,
                asset_id,
                allocation["date"],
                current_date,
                target_weight,
                current_weight,
                len(pending_records),
            )
            pending_records.append(record)
            deferred.append(record)

    cash = nav - sum(positions.values())
    actual_weights = _weights(positions, cash, nav)
    requested_cash = sum(translated["cash_breakdown"].values())
    deferred_cash_offset = sum(row["deferred_weight_delta"] for row in deferred)
    position_errors = {
        asset_id: round(
            requested_targets.get(asset_id, 0.0)
            - actual_weights.get(asset_id, 0.0)
            - sum(
                row["deferred_weight_delta"]
                for row in deferred
                if row["instrument_id"] == asset_id
            ),
            10,
        )
        for asset_id in sorted(all_assets)
    }
    cash_error = actual_weights["CASH"] - requested_cash - deferred_cash_offset
    reconciliation = {
        "requested_weight_sum": round(sum(requested_targets.values()) + requested_cash, 10),
        "actual_weight_sum": round(sum(actual_weights.values()), 10),
        "cash_breakdown_weight": round(requested_cash, 10),
        "actual_post_trade_cash_weight": actual_weights["CASH"],
        "deferred_cash_offset": round(deferred_cash_offset, 10),
        "cash_reconciliation_error": round(cash_error, 10),
        "position_reconciliation_errors": position_errors,
        "verified": abs(cash_error) < 1e-8 and all(abs(value) < 1e-8 for value in position_errors.values()),
    }
    pending_ids = [row["instrument_id"] for row in deferred]
    event = {
        "event_id": event_id,
        "event_type": "signal_rebalance",
        "signal_date": allocation["date"],
        "requested_execution_date": current_date,
        "scheduled_execution_date": current_date,
        "first_attempt_date": current_date,
        "actual_execution_date": None if deferred else current_date,
        "completion_date": None if deferred else current_date,
        "execution_status": "partially_completed" if deferred and executable_targets else "deferred" if deferred else "completed",
        "deferred_days": None if deferred else 0,
        "pending_instrument_ids": pending_ids,
        "completed_instrument_ids": sorted(executable_targets),
        "requested_target_weights": {**dict(sorted(requested_targets.items())), "CASH": round(requested_cash, 10)},
        "executable_target_weights": dict(sorted(executable_targets.items())),
        "actual_post_trade_weights": actual_weights,
        "actual_post_trade_cash_weight": actual_weights["CASH"],
        "weights": actual_weights,
        "cash_breakdown": {key: round(value, 10) for key, value in translated["cash_breakdown"].items()},
        "unavailable_entry_cash": {key: round(translated["cash_breakdown"].get(key, 0.0), 10) for key in GAP_KEYS},
        "deferred_adjustments": deferred,
        "actual_vs_target_weight_error": round(sum(abs(row["deferred_weight_delta"]) for row in deferred), 10),
        "cash_reconciliation": {key: value for key, value in reconciliation.items() if "position" not in key},
        "position_reconciliation": {"errors": position_errors, "verified": all(abs(value) < 1e-8 for value in position_errors.values())},
        "reconciliation": reconciliation,
        "translation_details": translated["details"],
        "transaction_cost": 0.0,
    }
    return cash, event


def _pending_record(event_id, asset_id, signal_date, scheduled_date, target_weight, current_weight, index):
    delta = target_weight - current_weight
    return {
        "adjustment_id": f"{event_id}-{asset_id}-{index + 1}",
        "parent_event_id": event_id,
        "instrument_id": asset_id,
        "signal_date": signal_date,
        "scheduled_execution_date": scheduled_date,
        "target_weight": round(target_weight, 10),
        "pre_trade_weight": round(current_weight, 10),
        "deferred_weight_delta": round(delta, 10),
        "direction": "increase" if delta > 0 else "reduce",
        "reason": "held_asset_missing_price",
        "status": "pending",
        "created_date": scheduled_date,
        "last_attempt_date": scheduled_date,
        "completed_date": None,
        "deferred_days": None,
        "superseded_by_signal_date": None,
    }


def _process_pending(current_date, dates, nav, positions, cash, last_prices, price_maps, pending_records, signal_events):
    attempts = []
    for record in pending_records:
        if record["status"] != "pending":
            continue
        record["last_attempt_date"] = current_date
        asset_id = record["instrument_id"]
        if current_date not in price_maps.get(asset_id, {}):
            continue
        current_value = positions.get(asset_id, 0.0)
        desired_value = nav * record["target_weight"]
        if desired_value > current_value + cash:
            desired_value = current_value + cash
        cash += current_value - desired_value
        if desired_value > 1e-12:
            positions[asset_id] = desired_value
            last_prices[asset_id] = price_maps[asset_id][current_date]
        else:
            positions.pop(asset_id, None)
            last_prices.pop(asset_id, None)
        achieved_weight = desired_value / nav if nav else 0.0
        completed = abs(achieved_weight - record["target_weight"]) < 1e-8
        if completed:
            record["status"] = "completed"
            record["completed_date"] = current_date
            record["deferred_days"] = _trade_day_distance(dates, record["scheduled_execution_date"], current_date)
        attempts.append(
            {
                "event_type": "pending_adjustment_attempt",
                "adjustment_id": record["adjustment_id"],
                "instrument_id": asset_id,
                "date": current_date,
                "status": record["status"],
                "target_weight": record["target_weight"],
                "actual_weight": round(achieved_weight, 10),
            }
        )
        _refresh_parent_event(
            record["parent_event_id"], current_date, dates, pending_records, signal_events,
            positions, cash, nav,
        )
    return cash, attempts


def _refresh_parent_event(parent_id, current_date, dates, pending_records, signal_events, positions, cash, nav):
    event = next((row for row in signal_events if row["event_id"] == parent_id), None)
    if not event:
        return
    children = [row for row in pending_records if row["parent_event_id"] == parent_id]
    active = [row for row in children if row["status"] == "pending"]
    event["pending_instrument_ids"] = [row["instrument_id"] for row in active]
    event["completed_instrument_ids"] = sorted(
        set(event["completed_instrument_ids"])
        | {row["instrument_id"] for row in children if row["status"] == "completed"}
    )
    if not active and all(row["status"] == "completed" for row in children):
        event["execution_status"] = "completed"
        event["completion_date"] = current_date
        event["actual_execution_date"] = current_date
        event["deferred_days"] = _trade_day_distance(dates, event["scheduled_execution_date"], current_date)
        event["completion_actual_weights"] = _weights(positions, cash, nav)


def _supersede_pending(current_date, signal_date, pending_records, signal_events):
    affected_parents = set()
    for row in pending_records:
        if row["status"] == "pending":
            row["status"] = "superseded"
            row["superseded_by_signal_date"] = signal_date
            row["last_attempt_date"] = current_date
            affected_parents.add(row["parent_event_id"])
    for event in signal_events:
        if event["event_id"] in affected_parents:
            event["pending_instrument_ids"] = []
            event["superseded_by_signal_date"] = signal_date


def _weights(positions, cash, nav):
    weights = {asset_id: round(value / nav, 10) for asset_id, value in sorted(positions.items())} if nav else {}
    weights["CASH"] = round(cash / nav, 10) if nav else 0.0
    return weights


def _gap_contract(events):
    count = len(events)
    non_cash = sum(1 - row["cash_breakdown"]["research_cash"] for row in events)
    gaps = [sum(row["cash_breakdown"].get(key, 0) for key in GAP_KEYS) for row in events]
    tradable = sum(1 - row["cash_breakdown"]["research_cash"] - gap for row, gap in zip(events, gaps))
    reason_average = {
        key: round(sum(row["cash_breakdown"].get(key, 0) for row in events) / count, 6) if count else 0.0
        for key in GAP_KEYS
    }
    return {
        "coverage_contract": {
            "schema_version": "2.0",
            "metrics": [
                {
                    "metric": "tradable_weight_coverage",
                    "numerator": "actual_non_cash_etf_weight",
                    "denominator": "non_cash_research_weight",
                    "numerator_weight_period_sum": round(tradable, 10),
                    "denominator_weight_period_sum": round(non_cash, 10),
                    "formula": "actual_non_cash_etf_weight / non_cash_research_weight",
                    "unit": "fraction",
                    "value": round(tradable / non_cash, 6) if non_cash else 0.0,
                },
                {
                    "metric": "tradable_weight_coverage_total_portfolio",
                    "numerator": "actual_non_cash_etf_weight",
                    "denominator": "total_research_portfolio_weight",
                    "numerator_weight_period_sum": round(tradable, 10),
                    "denominator_weight_period_sum": float(count),
                    "formula": "actual_non_cash_etf_weight / total_research_portfolio_weight",
                    "unit": "fraction",
                    "value": round(tradable / count, 6) if count else 0.0,
                },
            ],
        },
        "gap_metrics": {
            "binary_any_gap_month_ratio": round(sum(value > 1e-10 for value in gaps) / count, 6) if count else 0.0,
            "average_gap_weight": round(sum(gaps) / count, 6) if count else 0.0,
            "median_gap_weight": round(median(gaps), 6) if gaps else 0.0,
            "max_gap_weight": round(max(gaps), 6) if gaps else 0.0,
            "frozen_positions_excluded_from_cash_gap": True,
        },
        "reason_average_weights": reason_average,
    }


def _comparison(v1, v2_curve, period, events, timeline_rows, stale_periods):
    v1_period_rows = [row for row in v1.get("equity_curve", []) if period["start"] <= row["date"] <= period["end"]]
    v2_period_rows = [row for row in v2_curve if period["start"] <= row["date"] <= period["end"]]
    v1_by_date = {row["date"]: row for row in v1_period_rows}
    v2_by_date = {row["date"]: row for row in v2_period_rows}
    shared_dates = sorted(set(v1_by_date) & set(v2_by_date))
    exact_v1 = _normalize([v1_by_date[value] for value in shared_dates])
    exact_v2 = _normalize([v2_by_date[value] for value in shared_dates])
    aligned_v1 = _forward_fill(v1_period_rows, [row["date"] for row in v2_period_rows])
    aligned_v2 = _normalize(v2_period_rows)
    v1_dates = {row["date"] for row in v1.get("equity_curve", [])}
    v2_dates = {row["date"] for row in v2_curve}
    missing_portfolio_days = len(stale_periods)
    late_weight = sum(event["cash_breakdown"]["not_yet_investable_cash"] for event in events)
    return {
        "available": True,
        "status": "neutral_attribution_only",
        "interpretation": "Metric differences are descriptive and do not establish V2 superiority.",
        "legacy_as_reported": {
            "v1_period": v1.get("period"),
            "v1_metrics": v1.get("metrics", {}),
            "v2_period": {"start": v2_curve[0]["date"], "end": v2_curve[-1]["date"]},
            "v2_metrics": build_metrics(v2_curve),
        },
        "exact_shared_observation_dates": {
            "period": {"start": shared_dates[0], "end": shared_dates[-1]},
            "shared_date_count": len(shared_dates),
            "v1_observation_count": len(exact_v1),
            "v2_observation_count": len(exact_v2),
            "date_set_hash": _hash_json(shared_dates),
            "v1_metrics": {**build_metrics(exact_v1), "dated": _dated_metrics(exact_v1)},
            "v2_metrics": {**build_metrics(exact_v2), "dated": _dated_metrics(exact_v2)},
        },
        "master_calendar_aligned": {
            "period": period,
            "aligned_date_count": len(aligned_v2),
            "carried_forward_v1_days": len(aligned_v2) - len(v1_period_rows),
            "v1_forward_fill_is_analysis_only": True,
            "v1_metrics": {**build_metrics(aligned_v1), "dated": _dated_metrics(aligned_v1)},
            "v2_metrics": {**build_metrics(aligned_v2), "dated": _dated_metrics(aligned_v2)},
        },
        "attribution": {
            "calendar_deletion_contribution": {
                "retained_days": len(v2_dates - v1_dates),
                "interpretation": "difference between exact-shared and master-aligned analytical views",
            },
            "late_etf_effect": {
                "target_weight_period_sum": round(late_weight, 10),
                "return_contribution_available": False,
                "reason": "B1 has no isolated counterfactual simulator for late-ETF returns",
            },
            "missing_price_effect": {
                "timeline_missing_rows": sum(row["state"] == "unknown_missing_price" for row in timeline_rows),
                "affected_held_portfolio_days": missing_portfolio_days,
                "return_contribution": 0.0 if missing_portfolio_days == 0 else None,
            },
            "timing_policy_contribution": {
                "available": False,
                "reason": "same-day counterfactual is intentionally not generated",
            },
            "unexplained_residual": {"available": False, "reason": "component return counterfactuals are not part of B1"},
        },
        "v1_period": v1.get("period"),
        "v2_simulation_period": {"start": v2_curve[0]["date"], "end": v2_curve[-1]["date"]},
        "common_comparison_period": period,
        "v1_common_metrics": build_metrics(exact_v1),
        "v2_common_metrics": build_metrics(exact_v2),
        "days_retained_that_v1_deleted": len(v2_dates - v1_dates),
        "period_extension_days": sum(row["date"] < v1["period"]["start"] for row in v2_curve),
        "v1_report_sha256": _sha(ROOT / "reports" / "execution_backtest_report.json"),
        "eligible_to_replace_v1": False,
    }


def _forward_fill(rows, target_dates):
    by_date = {row["date"]: row["value"] for row in rows}
    last = None
    result = []
    for value in target_dates:
        if value in by_date:
            last = by_date[value]
        if last is not None:
            result.append({"date": value, "value": last})
    return _normalize(result)


def _dated_metrics(curve):
    if len(curve) < 2:
        return {"observation_count": len(curve), "observation_count_annualized": None, "elapsed_calendar_time_annualized": None}
    normalized = _normalize(curve)
    observation = build_metrics(normalized)["annual_return"]
    elapsed_years = (Date.fromisoformat(curve[-1]["date"]) - Date.fromisoformat(curve[0]["date"])).days / 365.2425
    elapsed = (normalized[-1]["value"] ** (1 / elapsed_years) - 1) if elapsed_years > 0 else None
    return {
        "observation_count": len(curve),
        "elapsed_calendar_days": (Date.fromisoformat(curve[-1]["date"]) - Date.fromisoformat(curve[0]["date"])).days,
        "observation_count_annualized": round(observation, 6),
        "elapsed_calendar_time_annualized": round(elapsed, 6) if elapsed is not None else None,
    }


def _normalize(rows):
    if not rows:
        return []
    base = rows[0]["value"]
    return [{"date": row["date"], "value": row["value"] / base} for row in rows]


def _timeline_summary(rows, stale_valuation_days):
    counts = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    return {"state_counts": counts, "timeline_row_count": len(rows), "stale_valuation_days": stale_valuation_days}


def _deferred_summary(records):
    return {
        "created_count": len(records),
        "completed_count": sum(row["status"] == "completed" for row in records),
        "pending_count": sum(row["status"] == "pending" for row in records),
        "superseded_count": sum(row["status"] == "superseded" for row in records),
        "deferred_held_adjustment_weight": round(sum(abs(row["deferred_weight_delta"]) for row in records), 10),
        "frozen_position_weight": round(sum(row["pre_trade_weight"] for row in records), 10),
        "pending_exit_weight": round(sum(abs(row["deferred_weight_delta"]) for row in records if row["direction"] == "reduce"), 10),
        "pending_entry_adjustment_weight": round(sum(row["deferred_weight_delta"] for row in records if row["direction"] == "increase"), 10),
    }


def _validate_price_metadata_contract(price_maps, metadata):
    if set(price_maps) != set(metadata):
        raise ValueError("execution price and metadata instrument sets must match")
    for asset_id, prices in price_maps.items():
        if prices and min(prices) < metadata[asset_id]["listing_date"]:
            raise ValueError(f"ETF price predates listing_date: {asset_id}")


def _trade_day_distance(dates, start, end):
    return dates.index(end) - dates.index(start)


def _source_manifest():
    paths = [
        "reports/research_backtest_report.json",
        "reports/execution_backtest_report.json",
        "reports/execution_price_dataset_manifest.json",
        "data/universe/asset_mapping.json",
        "data/universe/execution_mapping_decision_ledger.json",
        "data/universe/execution_instrument_metadata.json",
        "data/market/cn_equity_trade_calendar.json",
        "backtest/execution/v2/engine.py",
        "backtest/execution/v2/investability.py",
        "backtest/execution/v2/calendar.py",
        "backtest/execution/v2/report.py",
        "backtest/execution/v2/models.py",
    ]
    manifest = {path: {"sha256": _sha(ROOT / path)} for path in paths}
    price_manifest = json.loads((ROOT / "reports" / "execution_price_dataset_manifest.json").read_text(encoding="utf-8"))
    for instrument_id, details in price_manifest.get("files", {}).items():
        path = f"data/execution_prices/{instrument_id.replace('.', '_')}.json"
        digest = _sha(ROOT / path)
        manifest[path] = {
            "sha256": digest,
            "declared_sha256": details.get("sha256"),
            "declared_hash_matches": digest == details.get("sha256"),
        }
    return manifest


def _hash_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
