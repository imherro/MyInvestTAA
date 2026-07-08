from __future__ import annotations


def selection_reasons(score: dict) -> list[str]:
    reasons: list[str] = []
    if float(score.get("theme_momentum_score", 0.0)) >= 70.0:
        reasons.append("Theme momentum high")
    if float(score.get("stock_breadth_score", 0.0)) >= 60.0:
        reasons.append("Stock breadth improving")
    if float(score.get("breadth_score", 0.0)) >= 60.0:
        reasons.append("Breadth improving")
    if float(score.get("relative_strength_score", 0.0)) >= 70.0:
        reasons.append("Relative strength top tier")
    if float(score.get("trend_score", 0.0)) >= 60.0:
        reasons.append("Trend supportive")
    if float(score.get("quality_score", 0.0)) >= 60.0:
        reasons.append("Quality anchor acceptable")
    return reasons or ["Mixed selection evidence"]


def build_selection_analysis(backtest_result: dict, limit: int = 10) -> dict:
    states = [
        state for state in backtest_result.get("states", [])
        if state.get("signals", {}).get("scores")
    ]
    if not states:
        return {"version": backtest_result.get("assumptions", {}).get("score_version"), "rows": []}
    latest = states[-1]
    rows = []
    for item in latest["signals"]["scores"][:limit]:
        rows.append(
            {
                "asset": item["id"],
                "name": item.get("name"),
                "theme": item.get("theme", "unclassified"),
                "opportunity_score": item.get("opportunity_score", 0.0),
                "relative_strength_score": item.get("relative_strength_score", 0.0),
                "theme_momentum_score": item.get("theme_momentum_score", 0.0),
                "breadth_score": item.get("breadth_score", 0.0),
                "stock_breadth_score": item.get("stock_breadth_score", item.get("breadth_score", 0.0)),
                "stock_breadth": item.get("stock_breadth", {}),
                "trend_score": item.get("trend_score", 0.0),
                "selection_reason": item.get("selection_reason") or selection_reasons(item),
            }
        )
    return {
        "version": backtest_result.get("assumptions", {}).get("score_version"),
        "date": latest.get("date"),
        "rows": rows,
    }
