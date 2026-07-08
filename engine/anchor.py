from __future__ import annotations


def calculate_anchor_score(asset: dict) -> float:
    score = float(asset.get("anchor_score", 0))
    if score < 0 or score > 100:
        raise ValueError(f"anchor_score must be between 0 and 100: {score}")
    return score


def anchor_level(score: float) -> str:
    if score >= 75:
        return "strong"
    if score >= 55:
        return "medium"
    if score >= 35:
        return "weak"
    return "fragile"

