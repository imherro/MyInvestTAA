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


def test_drawdown_events_api_returns_history_events():
    response = client.get("/api/drawdown/events/512890")

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "512890"
    assert len(payload["events"]) >= 1
    assert {"percentile", "zone", "event_count"} <= set(payload["current_pressure"])


def test_sample_backtest_api_returns_metrics():
    response = client.get("/api/backtest/sample")

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "512890"
    assert {"annual_return", "max_drawdown", "sharpe", "period"} <= set(payload)
