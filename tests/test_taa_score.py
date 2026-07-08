from engine.asset_repository import load_assets
from engine.taa_score import build_taa_ranking, recommendation


def test_build_taa_ranking_returns_assets_sorted_by_score():
    ranking = build_taa_ranking(load_assets())

    assert len(ranking) >= 5
    scores = [item["taa_score"] for item in ranking]
    assert scores == sorted(scores, reverse=True)
    assert {"id", "name", "drawdown", "anchor_score", "taa_score", "recommendation"} <= set(
        ranking[0]
    )


def test_recommendation_thresholds():
    assert recommendation(80) == "overweight"
    assert recommendation(65) == "watch_overweight"
    assert recommendation(50) == "neutral"
    assert recommendation(35) == "underweight"
    assert recommendation(20) == "avoid"

