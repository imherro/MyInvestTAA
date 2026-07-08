from __future__ import annotations

from engine.allocation.models import AllocationItem, AllocationRecommendation
from engine.asset_repository import load_price_history
from engine.opportunity import build_opportunity_ranking
from engine.regime import MarketRegime, detect_market_regime
from engine.risk import RiskBudget, build_risk_budget


def build_allocation_recommendation(
    assets: list[dict],
    max_weight: float = 40.0,
    min_cash: float = 10.0,
    regime: MarketRegime | None = None,
    risk_budget: RiskBudget | None = None,
) -> AllocationRecommendation:
    if max_weight <= 0 or max_weight > 100:
        raise ValueError("max_weight must be within (0, 100]")
    if min_cash < 0 or min_cash > 100:
        raise ValueError("min_cash must be within [0, 100]")
    if regime is None:
        regime = detect_market_regime(load_price_history("510300"))
    if risk_budget is None:
        risk_budget = build_risk_budget(regime)

    max_weight = min(max_weight, risk_budget.max_single_asset)
    min_cash = max(min_cash, risk_budget.min_cash)

    if not assets:
        return _cash_only(max_weight=max_weight, min_cash=min_cash, regime=regime, risk_budget=risk_budget)

    asset_by_id = {asset["id"]: asset for asset in assets}
    candidates = [
        item for item in build_opportunity_ranking(assets) if item["opportunity_score"] > 0
    ]
    invest_budget = min(100.0 - min_cash, risk_budget.equity_limit)

    if not candidates or invest_budget <= 0:
        return _cash_only(max_weight=max_weight, min_cash=min_cash, regime=regime, risk_budget=risk_budget)

    weights = _allocate_capped(candidates, invest_budget=invest_budget, max_weight=max_weight)
    allocation = []
    for item in candidates:
        weight = round(weights.get(item["id"], 0.0), 2)
        if weight <= 0:
            continue
        strategic = float(asset_by_id[item["id"]].get("strategic_weight_pct", 0))
        allocation.append(
            AllocationItem(
                asset_id=item["id"],
                name=item["name"],
                weight=weight,
                status=_status(weight, strategic),
                opportunity_score=item["opportunity_score"],
            )
        )

    allocation = _enforce_cash_floor_after_rounding(allocation, min_cash)
    cash_weight = round(100.0 - sum(item.weight for item in allocation), 2)
    allocation.append(
        AllocationItem(
            asset_id="CASH",
            name="Cash",
            weight=cash_weight,
            status="reserve",
            opportunity_score=None,
        )
    )

    return AllocationRecommendation(
        risk_level="neutral",
        max_weight=max_weight,
        min_cash=min_cash,
        market_regime=regime.state,
        equity_limit=risk_budget.equity_limit,
        cash_weight=cash_weight,
        allocation=allocation,
    )


def _enforce_cash_floor_after_rounding(
    allocation: list[AllocationItem],
    min_cash: float,
) -> list[AllocationItem]:
    max_invested = round(100.0 - min_cash, 2)
    invested = round(sum(item.weight for item in allocation), 2)
    excess = round(invested - max_invested, 2)
    if excess <= 0 or not allocation:
        return allocation

    largest = max(allocation, key=lambda item: item.weight)
    adjusted: list[AllocationItem] = []
    for item in allocation:
        if item.asset_id == largest.asset_id:
            adjusted.append(
                AllocationItem(
                    asset_id=item.asset_id,
                    name=item.name,
                    weight=round(item.weight - excess, 2),
                    status=item.status,
                    opportunity_score=item.opportunity_score,
                )
            )
        else:
            adjusted.append(item)
    return adjusted


def _allocate_capped(candidates: list[dict], invest_budget: float, max_weight: float) -> dict[str, float]:
    scores = {item["id"]: float(item["confidence_adjusted_score"]) for item in candidates}
    weights = {asset_id: 0.0 for asset_id in scores}
    remaining = invest_budget
    open_ids = set(scores)

    while remaining > 0.0001 and open_ids:
        total_score = sum(scores[asset_id] for asset_id in open_ids)
        if total_score <= 0:
            break
        allocated_this_round = 0.0
        closed: set[str] = set()
        for asset_id in list(open_ids):
            proposed = remaining * scores[asset_id] / total_score
            room = max_weight - weights[asset_id]
            add = min(proposed, room)
            weights[asset_id] += add
            allocated_this_round += add
            if weights[asset_id] >= max_weight - 0.0001:
                closed.add(asset_id)
        remaining -= allocated_this_round
        open_ids -= closed
        if allocated_this_round <= 0.0001:
            break

    return weights


def _cash_only(
    max_weight: float,
    min_cash: float,
    regime: MarketRegime,
    risk_budget: RiskBudget,
) -> AllocationRecommendation:
    return AllocationRecommendation(
        risk_level="defensive",
        max_weight=max_weight,
        min_cash=min_cash,
        market_regime=regime.state,
        equity_limit=risk_budget.equity_limit,
        cash_weight=100.0,
        allocation=[
            AllocationItem(
                asset_id="CASH",
                name="Cash",
                weight=100.0,
                status="reserve",
                opportunity_score=None,
            )
        ],
    )


def _status(weight: float, strategic_weight: float) -> str:
    if weight > strategic_weight + 0.01:
        return "overweight"
    if weight < strategic_weight - 0.01:
        return "underweight"
    return "neutral"
