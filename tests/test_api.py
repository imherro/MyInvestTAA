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


def test_recovery_api_returns_summary():
    response = client.get("/api/recovery/512890")

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "512890"
    assert {"event_count", "recovered_events", "recovery_probability", "events"} <= set(payload)


def test_opportunity_ranking_api_returns_scores():
    response = client.get("/api/opportunity/ranking")

    assert response.status_code == 200
    ranking = response.json()
    assert len(ranking) >= 5
    assert {"drawdown_pressure", "recovery_probability", "opportunity_score"} <= set(ranking[0])


def test_anchor_profiles_api_returns_profiles():
    response = client.get("/api/anchor/profiles")

    assert response.status_code == 200
    profiles = response.json()
    assert len(profiles) >= 5
    assert {"asset_id", "anchor_score", "confidence"} <= set(profiles[0])


def test_allocation_recommendation_api_returns_weights():
    response = client.get("/api/allocation/recommendation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_weight"] == 100.0
    assert "market_regime" in payload
    assert "equity_limit" in payload
    assert "cash_weight" in payload
    assert any(item["asset_id"] == "CASH" for item in payload["allocation"])


def test_regime_current_api_returns_state():
    response = client.get("/api/regime/current")

    assert response.status_code == 200
    payload = response.json()
    assert {"state", "confidence", "equity_limit", "description"} <= set(payload)


def test_risk_budget_api_returns_limits():
    response = client.get("/api/risk/budget")

    assert response.status_code == 200
    payload = response.json()
    assert {"regime_state", "equity_limit", "min_cash", "max_single_asset"} <= set(payload)
