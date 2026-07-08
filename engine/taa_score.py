from __future__ import annotations

from engine.anchor import anchor_level, calculate_anchor_score
from engine.drawdown import calculate_drawdown, drawdown_score


def build_taa_ranking(assets: list[dict]) -> list[dict]:
    ranking = [score_asset(asset) for asset in assets]
    return sorted(ranking, key=lambda item: item["taa_score"], reverse=True)


def score_asset(asset: dict) -> dict:
    drawdown = calculate_drawdown([float(price) for price in asset["prices"]])
    drawdown_component = drawdown_score(drawdown)
    anchor_component = calculate_anchor_score(asset)
    placeholder_component = float(asset.get("placeholder_score", 50))

    taa_score = round(
        0.4 * drawdown_component
        + 0.3 * anchor_component
        + 0.3 * placeholder_component,
        2,
    )

    return {
        "id": asset["id"],
        "name": asset["name"],
        "category": asset["category"],
        "risk_level": asset.get("risk_level", "unknown"),
        "strategic_weight_pct": asset.get("strategic_weight_pct"),
        "current_weight_pct": asset.get("current_weight_pct"),
        "drawdown": drawdown.as_dict(),
        "drawdown_score": drawdown_component,
        "anchor_score": anchor_component,
        "anchor_level": anchor_level(anchor_component),
        "placeholder_score": placeholder_component,
        "taa_score": taa_score,
        "recommendation": recommendation(taa_score),
    }


def recommendation(taa_score: float) -> str:
    if taa_score >= 75:
        return "overweight"
    if taa_score >= 60:
        return "watch_overweight"
    if taa_score >= 45:
        return "neutral"
    if taa_score >= 30:
        return "underweight"
    return "avoid"

