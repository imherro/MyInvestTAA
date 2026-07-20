from fastapi.testclient import TestClient

from backend.main import app


CLIENT = TestClient(app)
CURRENT_ROUTES = {
    "/", "/strategies", "/strategies/current-taa", "/strategies/p2-style-drawdown",
    "/allocation", "/research", "/shadow", "/data", "/site-map",
}


def test_public_business_routes_are_exactly_the_strategy_and_report_pages() -> None:
    routes = {
        route.path
        for route in app.routes
        if "GET" in getattr(route, "methods", set())
    }
    assert routes == CURRENT_ROUTES


def test_each_public_page_is_available() -> None:
    for path in CURRENT_ROUTES:
        response = CLIENT.get(path)
        assert response.status_code == 200
        assert "CURRENT_TAA" in response.text


def test_old_pages_and_apis_are_not_public() -> None:
    old_paths = (
        "/current-decision",
        "/v11-current-allocation",
        "/research-validation",
        "/system-status",
        "/research-backtest",
        "/execution-backtest",
        "/shadow-portfolio",
        "/api/assets",
        "/api/decision/v11-current-allocation",
        "/docs",
        "/redoc",
        "/openapi.json",
    )
    for path in old_paths:
        assert CLIENT.get(path).status_code == 404
