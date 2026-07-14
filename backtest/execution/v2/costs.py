from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path

from backtest.execution.v2.cost_domain import (
    SERIALIZATION_DECIMALS,
    VALUE_TOLERANCE,
    ZERO_POSITION_TOLERANCE,
    CostPolicy,
    ExecutedAdjustment,
)
from engine.asset_registry.loader import ROOT


POLICY_PATH = ROOT / "config" / "execution_v2_cost_policy.json"


def load_cost_policy(path: Path | None = None) -> CostPolicy:
    target = path or POLICY_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    required = {
        "schema_version", "policy_id", "scenario_id", "effective_date", "commission", "slippage",
        "tax", "fund_expense_treatment", "cash_yield", "assumption_source", "evidence_status",
        "production_approved", "verified",
    }
    if not required.issubset(raw) or raw["schema_version"] != "1.0":
        raise ValueError("cost policy required fields or schema are invalid")
    try:
        date.fromisoformat(raw["effective_date"])
        rates = [
            raw["commission"]["buy_bps"], raw["commission"]["sell_bps"],
            raw["slippage"]["buy_bps"], raw["slippage"]["sell_bps"],
            raw["tax"]["buy_bps"], raw["tax"]["sell_bps"],
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("cost policy date or rate fields are invalid") from exc
    if (
        not raw["policy_id"] or not raw["scenario_id"]
        or any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in rates)
        or raw["verified"] is not True or raw["tax"].get("verified") is not True
        or raw["fund_expense_treatment"] != "embedded_in_qfq_market_price"
        or raw["cash_yield"] != 0
        or not isinstance(raw["assumption_source"], str) or "research" not in raw["assumption_source"].lower()
        or raw["evidence_status"] != "research_assumption_not_market_verified"
        or raw["production_approved"] is not False
        or raw["commission"].get("minimum_fee_enabled") is not False
    ):
        raise ValueError("cost policy contract is invalid")
    return CostPolicy(
        policy_id=raw["policy_id"], scenario_id=raw["scenario_id"], effective_date=raw["effective_date"],
        commission_buy_bps=float(rates[0]), commission_sell_bps=float(rates[1]),
        slippage_buy_bps=float(rates[2]), slippage_sell_bps=float(rates[3]),
        tax_buy_bps=float(rates[4]), tax_sell_bps=float(rates[5]),
        assumption_source=raw["assumption_source"], evidence_status=raw["evidence_status"],
        production_approved=raw["production_approved"],
        policy_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    )


def execute_targets_with_costs(
    *, date_value, parent_event_id, pending_adjustment_id, positions, cash, targets, policy,
    event_pre_trade_nav, sequence_start=1, mapping_quality=None,
):
    mapping_quality = mapping_quality or {}
    pre_values = {asset_id: positions.get(asset_id, 0.0) for asset_id in set(positions) | set(targets)}
    sells = {asset_id: target for asset_id, target in targets.items() if target < pre_values.get(asset_id, 0.0) - VALUE_TOLERANCE}
    buys = {asset_id: target for asset_id, target in targets.items() if target > pre_values.get(asset_id, 0.0) + VALUE_TOLERANCE}
    ledger = []
    sequence = sequence_start

    for asset_id, target in sorted(sells.items()):
        pre = positions.get(asset_id, 0.0)
        notional = pre - target
        costs = _costs(notional, "sell", policy)
        pre_cash = cash
        cash += notional - costs["total_cost"]
        cash = _validated_cash(cash)
        if target > ZERO_POSITION_TOLERANCE:
            positions[asset_id] = target
        else:
            positions.pop(asset_id, None)
        ledger.append(_adjustment(
            date_value, parent_event_id, pending_adjustment_id, asset_id, "sell", pre, target,
            target, notional, costs, mapping_quality.get(asset_id, "unknown"), sequence,
            pre_cash, cash, event_pre_trade_nav,
        ))
        sequence += 1

    requested_buy = sum(target - positions.get(asset_id, 0.0) for asset_id, target in buys.items())
    weighted_rate = max((_total_rate("buy", policy) for _ in buys), default=0.0)
    capacity = cash / (1 + weighted_rate / 10000) if cash > 0 else 0.0
    scale = min(1.0, capacity / requested_buy) if requested_buy > VALUE_TOLERANCE else 1.0
    residual = 0.0
    for asset_id, target in sorted(buys.items()):
        pre = positions.get(asset_id, 0.0)
        requested = target - pre
        notional = requested * scale
        executed = pre + notional
        costs = _costs(notional, "buy", policy)
        pre_cash = cash
        cash -= notional + costs["total_cost"]
        cash = _validated_cash(cash)
        positions[asset_id] = executed
        residual += requested - notional
        if notional > VALUE_TOLERANCE:
            ledger.append(_adjustment(
                date_value, parent_event_id, pending_adjustment_id, asset_id, "buy", pre,
                target, executed, notional, costs, mapping_quality.get(asset_id, "unknown"),
                sequence, pre_cash, cash, event_pre_trade_nav,
            ))
            sequence += 1
    event_cost = sum(row["total_cost"] for row in ledger)
    event_post_trade_nav = cash + sum(positions.values())
    if abs(event_post_trade_nav - (event_pre_trade_nav - event_cost)) > VALUE_TOLERANCE:
        raise ValueError("event cost accounting bridge does not reconcile")
    for row in ledger:
        row["event_post_trade_nav"] = round(event_post_trade_nav, SERIALIZATION_DECIMALS)
    return cash, ledger, {
        "requested_buy_notional": round(requested_buy, SERIALIZATION_DECIMALS),
        "executed_buy_notional": round(requested_buy - residual, SERIALIZATION_DECIMALS),
        "cost_constrained_target_residual": round(residual, SERIALIZATION_DECIMALS),
        "buy_scale": round(scale, SERIALIZATION_DECIMALS),
    }


def _costs(notional, direction, policy):
    commission = notional * getattr(policy, f"commission_{direction}_bps") / 10000
    slippage = notional * getattr(policy, f"slippage_{direction}_bps") / 10000
    tax = notional * getattr(policy, f"tax_{direction}_bps") / 10000
    return {
        "commission_cost": round(commission, SERIALIZATION_DECIMALS),
        "slippage_cost": round(slippage, SERIALIZATION_DECIMALS),
        "tax_cost": round(tax, SERIALIZATION_DECIMALS),
        "total_cost": round(commission + slippage + tax, SERIALIZATION_DECIMALS),
    }


def _total_rate(direction, policy):
    return getattr(policy, f"commission_{direction}_bps") + getattr(policy, f"slippage_{direction}_bps") + getattr(policy, f"tax_{direction}_bps")


def _validated_cash(value):
    if value < -VALUE_TOLERANCE:
        raise ValueError("cost execution produced negative cash")
    return 0.0 if value < 0 else value


def _adjustment(
    date_value, parent, pending, asset_id, direction, pre, requested, executed, notional,
    costs, quality, sequence, pre_cash, post_cash, event_pre_nav,
):
    return ExecutedAdjustment(
        adjustment_id=f"{parent}-{asset_id}-{direction}-{date_value}", sequence_number=sequence,
        parent_event_id=parent,
        pending_adjustment_id=pending, instrument_id=asset_id, execution_date=date_value,
        direction=direction, pre_trade_value=round(pre, SERIALIZATION_DECIMALS),
        requested_post_trade_value=round(requested, SERIALIZATION_DECIMALS),
        executed_post_trade_value=round(executed, SERIALIZATION_DECIMALS),
        gross_traded_notional=round(notional, SERIALIZATION_DECIMALS),
        commission_cost=round(costs["commission_cost"], SERIALIZATION_DECIMALS),
        slippage_cost=round(costs["slippage_cost"], SERIALIZATION_DECIMALS),
        tax_cost=round(costs["tax_cost"], SERIALIZATION_DECIMALS),
        total_cost=round(costs["total_cost"], SERIALIZATION_DECIMALS), status="completed",
        pre_trade_cash=round(pre_cash, SERIALIZATION_DECIMALS),
        post_trade_cash=round(post_cash, SERIALIZATION_DECIMALS),
        event_pre_trade_nav=round(event_pre_nav, SERIALIZATION_DECIMALS),
        event_post_trade_nav=0.0,
        mapping_quality=quality, reason="signal_rebalance" if pending is None else "completed_pending",
    ).as_dict()
