from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_assets_api_returns_sample_universe():
    response = client.get("/api/assets")

    assert response.status_code == 200
    assets = response.json()
    assert len(assets) >= 5
    assert {"id", "name", "anchor_score", "max_drawdown", "prices"} <= set(assets[0])


def test_taa_ranking_api_returns_ranked_scores():
    response = client.get("/api/taa/ranking")

    assert response.status_code == 200
    ranking = response.json()
    assert len(ranking) >= 5
    assert ranking[0]["taa_score"] >= ranking[-1]["taa_score"]
    assert {"drawdown", "drawdown_score", "anchor_score", "taa_score"} <= set(ranking[0])

