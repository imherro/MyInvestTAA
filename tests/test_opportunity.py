from engine.asset_repository import load_assets
from engine.opportunity import build_opportunity_ranking, score_asset_opportunity


def test_score_asset_opportunity_returns_pressure_and_recovery():
    asset = next(item for item in load_assets() if item["id"] == "512890")

    score = score_asset_opportunity(asset)

    assert score["id"] == "512890"
    assert 0 <= score["drawdown_pressure"] <= 100
    assert 0 <= score["recovery_probability"] <= 100
    assert 0 <= score["opportunity_score"] <= 100


def test_build_opportunity_ranking_sorts_descending():
    ranking = build_opportunity_ranking(load_assets())

    scores = [item["opportunity_score"] for item in ranking]
    assert len(ranking) >= 5
    assert scores == sorted(scores, reverse=True)

