from __future__ import annotations

from engine.allocation.allocator import _allocate_capped
from engine.risk.models import RiskBudget


def build_rebalance_weights(
    opportunity_scores: list[dict],
    risk_budget: RiskBudget,
) -> dict[str, float]:
    candidates = [
        item for item in opportunity_scores if item.get("confidence_adjusted_score", 0) > 0
    ]
    if not candidates:
        return {"CASH": 100.0}

    invest_budget = risk_budget.equity_limit
    raw_weights = _allocate_capped(
        candidates,
        invest_budget=invest_budget,
        max_weight=risk_budget.max_single_asset,
    )
    weights = {
        asset_id: round(weight, 4)
        for asset_id, weight in raw_weights.items()
        if round(weight, 4) > 0
    }
    weights["CASH"] = round(100.0 - sum(weights.values()), 4)
    return normalize_weights(weights)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return {"CASH": 100.0}
    normalized = {asset_id: round(weight / total * 100.0, 4) for asset_id, weight in weights.items()}
    drift = round(100.0 - sum(normalized.values()), 4)
    if drift:
        key = "CASH" if "CASH" in normalized else next(iter(normalized))
        normalized[key] = round(normalized[key] + drift, 4)
    return normalized


def turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    asset_ids = set(previous) | set(current)
    return round(sum(abs(current.get(asset_id, 0.0) - previous.get(asset_id, 0.0)) for asset_id in asset_ids) / 200.0, 4)

