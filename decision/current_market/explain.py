from __future__ import annotations


_CASH_LABELS = {
    "research_cash": "research strategy cash",
    "unmapped_cash": "unmapped research assets",
    "research_only_cash": "research-only assets without an approved execution ETF",
    "rejected_proxy_cash": "assets with a rejected execution proxy",
    "low_quality_proxy_cash": "assets with only a low-quality proxy",
    "missing_price_cash": "assets without a usable price snapshot",
}


def build_cash_explanation(cash_breakdown: dict, mapping_explanations: list[dict], cash_weight: float) -> dict:
    components = []
    for category, label in _CASH_LABELS.items():
        weight = float(cash_breakdown.get(category, 0))
        rows = [
            {
                "research_asset_id": row.get("research_asset_id"),
                "weight": float(row.get("research_weight", 0)),
                "reason": row.get("reason"),
            }
            for row in mapping_explanations
            if row.get("reason") == category and row.get("research_asset_id") != "CASH"
        ]
        assets: list | list[dict] = ["CASH"] if category == "research_cash" and weight else rows
        components.append(
            {
                "category": category,
                "weight": weight,
                "assets": assets,
                "explanation": label,
            }
        )
    total = round(sum(row["weight"] for row in components), 10)
    reconciled = abs(total - float(cash_weight)) <= 0.000001
    parts = []
    for component in components:
        if not component["weight"]:
            continue
        asset_ids = [
            row.get("research_asset_id")
            for row in component["assets"]
            if isinstance(row, dict) and row.get("research_asset_id")
        ]
        suffix = f" ({', '.join(asset_ids)})" if asset_ids else ""
        parts.append(
            f"{component['weight']:.0%} from {component['explanation']}{suffix}"
        )
    return {
        "total_cash_weight": float(cash_weight),
        "component_weight_sum": total,
        "reconciled": reconciled,
        "components": components,
        "text": (
            f"The {cash_weight:.0%} Shadow cash weight is not a single timing call: "
            + "; ".join(parts)
            + "."
        ),
    }


def decision_headline(*, status: str, ready_for_user_review: bool) -> str:
    if ready_for_user_review:
        return "Verified local allocation snapshot ready for user review"
    if status == "stale":
        return "Historical verified decision snapshot"
    return "Decision snapshot unavailable for user review"


def build_decision_summary(
    *,
    market_state: dict,
    shadow: dict,
    execution: dict,
    freshness: dict,
    cash_text: str,
    ready_for_user_review: bool,
    status: str,
    evidence_blockers: list[str],
) -> dict:
    historical = status == "stale"
    executable = [
        f"{asset_id}: {weight:.0%}"
        for asset_id, weight in shadow.get("execution_weights", {}).items()
        if asset_id != "CASH"
    ]
    not_executable = [
        f"{row.get('research_asset_id')}: {row.get('reason')}"
        for row in shadow.get("mapping_explanations", [])
        if row.get("destination") == "CASH" and row.get("research_asset_id") != "CASH"
    ]
    return {
        "headline": decision_headline(
            status=status, ready_for_user_review=ready_for_user_review
        ),
        "current_stance": (
            "Side-by-side review only; no production action is created."
            if not historical
            else "Snapshot is stale and must be read as historical context only."
        ),
        "what_is_executable": executable,
        "what_is_not_executable": not_executable,
        "user_interpretation": [
            f"Market regime is {market_state.get('regime', 'unavailable')}.",
            cash_text,
            "V11 remains unchanged; Research and Shadow do not replace it.",
        ],
        "blocking_conditions": list(dict.fromkeys(evidence_blockers)),
    }
