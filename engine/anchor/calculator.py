from __future__ import annotations

from engine.anchor.models import AssetAnchorProfile


REQUIRED_SCORE_FIELDS = (
    "cashflow_score",
    "profitability_score",
    "balance_sheet_score",
    "valuation_anchor_score",
    "lifecycle_score",
)


def calculate_anchor_score(asset: dict) -> float:
    asset_id = asset.get("id")
    if asset_id:
        from engine.anchor.config import load_anchor_profile

        profile = load_anchor_profile(str(asset_id))
        if profile:
            return profile.anchor_score

    score = float(asset.get("anchor_score", 0))
    _validate_score(score, "anchor_score")
    return score


def calculate_profile_anchor_score(profile: dict) -> AssetAnchorProfile:
    missing = [field for field in REQUIRED_SCORE_FIELDS if field not in profile]
    if missing:
        raise ValueError(f"anchor profile missing fields: {missing}")

    scores = {field: float(profile[field]) for field in REQUIRED_SCORE_FIELDS}
    for field, score in scores.items():
        _validate_score(score, field)

    anchor_score = round(
        0.25 * scores["cashflow_score"]
        + 0.25 * scores["profitability_score"]
        + 0.20 * scores["balance_sheet_score"]
        + 0.20 * scores["valuation_anchor_score"]
        + 0.10 * scores["lifecycle_score"],
        2,
    )

    return AssetAnchorProfile(
        asset_id=str(profile.get("id") or profile.get("asset_id")),
        cashflow_score=scores["cashflow_score"],
        profitability_score=scores["profitability_score"],
        balance_sheet_score=scores["balance_sheet_score"],
        valuation_anchor_score=scores["valuation_anchor_score"],
        lifecycle_score=scores["lifecycle_score"],
        anchor_score=anchor_score,
        confidence=str(profile.get("confidence", _confidence_from_score(anchor_score))),
    )


def anchor_level(score: float) -> str:
    if score >= 75:
        return "strong"
    if score >= 55:
        return "medium"
    if score >= 35:
        return "weak"
    return "fragile"


def _validate_score(score: float, field: str) -> None:
    if score < 0 or score > 100:
        raise ValueError(f"{field} must be between 0 and 100: {score}")


def _confidence_from_score(score: float) -> str:
    if score >= 70:
        return "medium"
    if score >= 45:
        return "low"
    return "low"
