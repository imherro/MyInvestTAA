from __future__ import annotations


def cash_explanation(cash_breakdown: dict) -> str:
    total = round(sum(float(value) for value in cash_breakdown.values()), 10)
    research = float(cash_breakdown.get("research_cash", 0))
    research_only = float(cash_breakdown.get("research_only_cash", 0))
    return (
        f"The {total:.0%} Shadow cash weight is not a single timing call: "
        f"{research:.0%} comes from the research strategy and "
        f"{research_only:.0%} comes from the research-only computing-power index "
        "(931688CNY010.CSI, 算力), which has no approved execution ETF. "
        "Any remaining cash would come from unmapped, rejected, low-quality, or missing-price assets."
    )


def build_decision_summary(*, market_state: dict, shadow: dict, execution: dict, freshness: dict, cash_text: str) -> dict:
    historical = freshness.get("status") != "pass"
    headline = (
        "Historical verified decision snapshot"
        if historical
        else "Verified local allocation snapshot ready for user review"
    )
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
    blocking = list(execution.get("reasons", [])) + list(freshness.get("errors", []))
    return {
        "headline": headline,
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
        "blocking_conditions": list(dict.fromkeys(blocking)),
    }
