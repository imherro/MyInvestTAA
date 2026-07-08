from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_dashboard_returns_strategy_comparison_sections():
    response = client.get("/")

    assert response.status_code == 200
    assert "Strategy Comparison" in response.text
    assert "收益曲线对比" in response.text


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


def test_taa_backtest_api_returns_strategy_metrics():
    response = client.get("/api/backtest/taa")

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy"] == "MyInvestTAA"
    assert {"annual_return", "max_drawdown", "sharpe", "calmar"} <= set(payload["metrics"])


def test_backtest_comparison_api_returns_alpha_metrics():
    response = client.get("/api/backtest/comparison")

    assert response.status_code == 200
    payload = response.json()
    assert "MyInvestTAA" in payload["strategies"]
    assert {"annual_return", "max_drawdown", "sharpe", "excess_return"} <= set(payload["rows"][0])


def test_research_evaluation_api_returns_rolling_metrics():
    response = client.get("/api/research/evaluation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy"] == "MyInvestTAA"
    assert {"rolling_win_rate", "avg_alpha", "windows"} <= set(payload)


def test_research_quality_api_returns_reports():
    response = client.get("/api/research/quality")

    assert response.status_code == 200
    payload = response.json()
    assert {"average_score", "reports", "asset_count"} <= set(payload)


def test_research_attribution_api_returns_contribution():
    response = client.get("/api/research/attribution")

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy"] == "MyInvestTAA"
    assert "contribution" in payload


def test_live_backtest_api_returns_database_report():
    response = client.get("/api/research/live-backtest")

    assert response.status_code == 200
    payload = response.json()
    assert {"data_source", "quality", "backtest", "benchmark", "attribution"} <= set(payload)


def test_real_performance_api_returns_dataset_version():
    response = client.get("/api/research/real-performance")

    assert response.status_code == 200
    payload = response.json()
    assert "dataset_version" in payload["data"]
    assert {"annual_return", "max_drawdown", "sharpe", "calmar"} <= set(payload["performance"])


def test_research_report_page_returns_sections():
    response = client.get("/research")

    assert response.status_code == 200
    assert "Research Report" in response.text
    assert "Rolling胜率" in response.text


def test_data_pipeline_page_returns_sections():
    response = client.get("/pipeline")

    assert response.status_code == 200
    assert "Data Pipeline" in response.text
    assert "真实回测报告" in response.text


def test_real_market_research_page_returns_sections():
    response = client.get("/real-research")

    assert response.status_code == 200
    assert "Real Market Research" in response.text
    assert "Dataset Version" in response.text


def test_data_quality_page_returns_sections():
    response = client.get("/quality")

    assert response.status_code == 200
    assert "Data Quality" in response.text
    assert "数据质量评分" in response.text


def test_attribution_page_returns_sections():
    response = client.get("/attribution")

    assert response.status_code == 200
    assert "Attribution" in response.text
    assert "收益来源" in response.text


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
