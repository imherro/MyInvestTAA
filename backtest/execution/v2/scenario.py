from __future__ import annotations

import hashlib
import json
from datetime import date as Date

from backtest.execution.v2.costs import execute_targets_with_costs
from backtest.execution.v2.cost_domain import SERIALIZATION_DECIMALS, VALUE_TOLERANCE
from backtest.research.metrics import build_metrics
from engine.asset_registry.loader import ROOT


def run_cost_scenario(b1_report, execution_price_data, policy, *, b1_output_set_hash):
    dates = [row["date"] for row in b1_report["daily_portfolio_states"]]
    price_maps = {asset_id: {row.date: row.close for row in rows} for asset_id, rows in execution_price_data.items()}
    b1_states = {row["date"]: row for row in b1_report["daily_portfolio_states"]}
    strategy = "EXECUTION_PROXY_V2_B2_COST_EXPERIMENTAL"
    date_grid_hash = _hash_json(dates)
    engine_sources = _engine_source_hashes()
    run_components = {
        "b1_input_source_manifest_hash": b1_report["input_source_manifest_hash"],
        "b1_output_set_hash": b1_output_set_hash,
        "cost_policy_hash": policy.policy_sha256,
        "scenario_id": policy.scenario_id,
        "master_date_grid_hash": date_grid_hash,
        "strategy": strategy,
        "engine_code_hash": _hash_json(engine_sources),
        "engine_source_hashes": engine_sources,
    }
    run_id = f"execution-v2-b2-cost-{_hash_json(run_components)[:16]}"
    positions = {}
    last_prices = {}
    cash = 1.0
    curve = []
    daily = []
    ledger = []
    cumulative_cost = 0.0
    cumulative_cost_curve = []

    for current_date in dates:
        opening_cash = cash
        opening_nav = cash + sum(positions.values())
        for asset_id, value in list(positions.items()):
            price = price_maps.get(asset_id, {}).get(current_date)
            previous = last_prices.get(asset_id)
            if price is not None and previous:
                positions[asset_id] = value * price / previous
                last_prices[asset_id] = price
            elif price is not None:
                last_prices[asset_id] = price
        pre_trade_nav = cash + sum(positions.values())
        day_ledger = []
        constraints = []
        for event in b1_states[current_date].get("execution_events", []):
            if event.get("event_type") == "signal_rebalance":
                actual_weights = event["actual_post_trade_weights"]
                deferred_ids = {row["instrument_id"] for row in event.get("deferred_adjustments", [])}
                instrument_ids = (set(positions) | set(actual_weights)) - deferred_ids - {"CASH"}
                targets = {
                    asset_id: pre_trade_nav * actual_weights.get(asset_id, 0.0)
                    for asset_id in instrument_ids
                }
                qualities = {
                    row["destination"]: row.get("mapping_quality", "unknown")
                    for row in event.get("translation_details", []) if row.get("destination") != "CASH"
                }
                cash, rows, constraint = execute_targets_with_costs(
                    date_value=current_date, parent_event_id=event["event_id"], pending_adjustment_id=None,
                    positions=positions, cash=cash, targets=targets, policy=policy, mapping_quality=qualities,
                )
            elif event.get("event_type") == "pending_adjustment_attempt" and event.get("status") == "completed":
                targets = {event["instrument_id"]: pre_trade_nav * event["target_weight"]}
                cash, rows, constraint = execute_targets_with_costs(
                    date_value=current_date, parent_event_id=event["adjustment_id"],
                    pending_adjustment_id=event["adjustment_id"], positions=positions, cash=cash,
                    targets=targets, policy=policy,
                )
            else:
                continue
            for row in rows:
                row.update({"run_id": run_id, "scenario_id": policy.scenario_id, "policy_id": policy.policy_id, "policy_sha256": policy.policy_sha256})
                if row["instrument_id"] in positions:
                    last_prices[row["instrument_id"]] = price_maps[row["instrument_id"]][current_date]
                else:
                    last_prices.pop(row["instrument_id"], None)
            day_ledger.extend(rows)
            constraints.append(constraint)
        day_cost = sum(row["total_cost"] for row in day_ledger)
        cumulative_cost += day_cost
        closing_nav = cash + sum(positions.values())
        if abs(closing_nav - (pre_trade_nav - day_cost)) > VALUE_TOLERANCE:
            raise ValueError("daily cost accounting bridge does not reconcile")
        for row in day_ledger:
            row["post_trade_cash"] = round(cash, SERIALIZATION_DECIMALS)
        ledger.extend(day_ledger)
        weights = {asset_id: round(value / closing_nav, SERIALIZATION_DECIMALS) for asset_id, value in sorted(positions.items())}
        weights["CASH"] = round(cash / closing_nav, SERIALIZATION_DECIMALS)
        curve.append({"date": current_date, "value": round(closing_nav, 8)})
        cumulative_cost_curve.append({"date": current_date, "value": round(cumulative_cost, SERIALIZATION_DECIMALS)})
        daily.append({
            "date": current_date, "opening_nav": round(opening_nav, 8),
            "market_return_pnl": round(pre_trade_nav - opening_nav, SERIALIZATION_DECIMALS),
            "pre_trade_nav": round(pre_trade_nav, 8), "gross_traded_notional": round(sum(row["gross_traded_notional"] for row in day_ledger), SERIALIZATION_DECIMALS),
            "transaction_cost": round(day_cost, SERIALIZATION_DECIMALS), "closing_nav": round(closing_nav, 8),
            "opening_cash": round(opening_cash, SERIALIZATION_DECIMALS),
            "closing_cash": round(cash, SERIALIZATION_DECIMALS), "weights": weights,
            "cost_constraints": constraints,
        })

    attribution = _attribution(ledger)
    report = {
        "available": True, "strategy": strategy, "engine_status": "experimental_validation_only",
        "eligible_to_replace_v1": False, "production_actionable": False, "run_id": run_id,
        "scenario_id": policy.scenario_id, "b1_baseline_run_id": b1_report["run_id"],
        "b1_output_set_hash": b1_output_set_hash, "run_identity_components": run_components,
        "policy": policy.as_dict(), "policy_sha256": policy.policy_sha256,
        "periods": b1_report["periods"], "metrics_gross_zero_cost": b1_report["metrics_net"],
        "metrics_net_cost": _metrics_with_dates(curve), "gross_zero_cost_curve": b1_report["equity_curve_net"],
        "net_cost_curve": curve, "cumulative_cost_curve": cumulative_cost_curve,
        "daily_portfolio_states": daily, "execution_events": b1_report["monthly_allocations"],
        "cost_attribution": attribution,
        "reconciliation": {
            "ledger_total_cost": attribution["total_cost"],
            "daily_total_cost": round(sum(row["transaction_cost"] for row in daily), SERIALIZATION_DECIMALS),
            "ending_nav_drag": round(b1_report["equity_curve_net"][-1]["value"] - curve[-1]["value"], SERIALIZATION_DECIMALS),
        },
        "source_manifest": _source_manifest(policy.policy_sha256),
        "warnings": ["Experimental cost-policy scenario only; not broker execution evidence.", "Cash yield is fixed at zero in B2-1.", "No orders, shares, quantities, or target prices are produced."],
        "validation": {"cash_yield_zero": True, "negative_cash_used": False, "b1_golden_unchanged": b1_report["b1_golden_freeze"]["verified"]},
    }
    ledger_report = {"available": True, "run_id": run_id, "scenario_id": policy.scenario_id, "policy_sha256": policy.policy_sha256, "rows": ledger, "summary": attribution}
    comparison = _comparison(b1_report, report)
    comparison.update({"run_id": run_id, "scenario_id": policy.scenario_id, "policy_sha256": policy.policy_sha256, "b1_output_set_hash": b1_output_set_hash, "date_grid_hash": date_grid_hash})
    return report, ledger_report, comparison


def expected_run_id(report):
    return f"execution-v2-b2-cost-{_hash_json(report['run_identity_components'])[:16]}"


def _attribution(rows):
    def total(key): return round(sum(row[key] for row in rows), SERIALIZATION_DECIMALS)
    by_instrument = {}
    by_year = {}
    by_quality = {}
    for row in rows:
        by_instrument[row["instrument_id"]] = by_instrument.get(row["instrument_id"], 0.0) + row["total_cost"]
        year = row["execution_date"][:4]
        by_year[year] = by_year.get(year, 0.0) + row["total_cost"]
        by_quality[row["mapping_quality"]] = by_quality.get(row["mapping_quality"], 0.0) + row["total_cost"]
    return {
        "buy_notional": round(sum(row["gross_traded_notional"] for row in rows if row["direction"] == "buy"), SERIALIZATION_DECIMALS),
        "sell_notional": round(sum(row["gross_traded_notional"] for row in rows if row["direction"] == "sell"), SERIALIZATION_DECIMALS),
        "total_notional": total("gross_traded_notional"), "commission_total": total("commission_cost"),
        "slippage_total": total("slippage_cost"), "tax_total": total("tax_cost"), "total_cost": total("total_cost"),
        "signal_rebalance_cost": round(sum(row["total_cost"] for row in rows if row["pending_adjustment_id"] is None), SERIALIZATION_DECIMALS),
        "completed_pending_cost": round(sum(row["total_cost"] for row in rows if row["pending_adjustment_id"] is not None), SERIALIZATION_DECIMALS),
        "cost_by_instrument": {key: round(value, SERIALIZATION_DECIMALS) for key, value in sorted(by_instrument.items())},
        "cost_by_year": {key: round(value, SERIALIZATION_DECIMALS) for key, value in sorted(by_year.items())},
        "cost_by_mapping_quality": {key: round(value, SERIALIZATION_DECIMALS) for key, value in sorted(by_quality.items())},
    }


def _comparison(b1, b2):
    gross = b1["metrics_net"]
    net = b2["metrics_net_cost"]
    return {
        "status": "neutral_cost_attribution_only", "date_grid_equal": [row["date"] for row in b1["equity_curve_net"]] == [row["date"] for row in b2["net_cost_curve"]],
        "b1_ending_nav": b1["equity_curve_net"][-1]["value"], "b2_ending_nav": b2["net_cost_curve"][-1]["value"],
        "annual_return_difference_percentage_points": round((net["annual_return"] - gross["annual_return"]) * 100, 6),
        "elapsed_calendar_annual_return_difference_percentage_points": round(
            (net["dated"]["elapsed_calendar_time_annualized"] - gross["dated"]["elapsed_calendar_time_annualized"]) * 100,
            6,
        ),
        "max_drawdown_difference_percentage_points": round((net["max_drawdown"] - gross["max_drawdown"]) * 100, 6),
        "sharpe_difference": round(net["sharpe"] - gross["sharpe"], 6),
        "cumulative_absolute_cost": b2["cost_attribution"]["total_cost"],
        "ending_nav_drag": b2["reconciliation"]["ending_nav_drag"],
        "turnover_notional_initial_nav_units": b2["cost_attribution"]["total_notional"],
        "turnover_denominator": "initial_portfolio_nav_1.0",
        "cost_per_unit_turnover": round(b2["cost_attribution"]["total_cost"] / b2["cost_attribution"]["total_notional"], 10) if b2["cost_attribution"]["total_notional"] else 0.0,
    }


def _source_manifest(policy_hash):
    paths = [
        "reports/execution_v2_COMMITTED.json",
        "reports/execution_v2_output_manifest.json",
        "config/execution_v2_cost_policy.json",
        "backtest/execution/v2/cost_domain.py",
        "backtest/execution/v2/costs.py",
        "backtest/execution/v2/scenario.py",
        "backtest/execution/v2/cost_validation.py",
        "scripts/run_execution_backtest_v2_b2_costs.py",
    ]
    return {path: {"sha256": _sha(ROOT / path)} for path in paths} | {"cost_policy": {"sha256": policy_hash}}


def _engine_source_hashes():
    paths = [
        "backtest/execution/v2/cost_domain.py",
        "backtest/execution/v2/costs.py",
        "backtest/execution/v2/scenario.py",
    ]
    return {path: _sha(ROOT / path) for path in paths}


def _metrics_with_dates(curve):
    metrics = build_metrics(curve)
    if len(curve) < 2:
        metrics["dated"] = {
            "observation_count": len(curve),
            "elapsed_calendar_days": 0,
            "observation_count_annualized": None,
            "elapsed_calendar_time_annualized": None,
        }
        return metrics
    elapsed_days = (Date.fromisoformat(curve[-1]["date"]) - Date.fromisoformat(curve[0]["date"])).days
    elapsed_years = elapsed_days / 365.2425
    base = curve[0]["value"]
    elapsed_return = (curve[-1]["value"] / base) ** (1 / elapsed_years) - 1 if base > 0 and elapsed_years > 0 else None
    metrics["dated"] = {
        "observation_count": len(curve),
        "elapsed_calendar_days": elapsed_days,
        "observation_count_annualized": metrics["annual_return"],
        "elapsed_calendar_time_annualized": round(elapsed_return, 6) if elapsed_return is not None else None,
    }
    return metrics


def _hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
