from fastapi.testclient import TestClient

from backend.main import app


CLIENT = TestClient(app)
CURRENT_ROUTES = {"/", "/allocation", "/research", "/shadow", "/data", "/site-map"}


def test_public_business_routes_are_exactly_the_six_current_pages() -> None:
    routes = {
        route.path
        for route in app.routes
        if "GET" in getattr(route, "methods", set())
    }
    assert routes == CURRENT_ROUTES


def test_each_current_page_is_available() -> None:
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
