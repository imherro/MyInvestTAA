from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_research_universe_api_returns_all_sections():
    response = client.get("/api/research/universe")

    assert response.status_code == 200
    payload = response.json()
    assert {"research_assets", "execution_assets", "mappings"} <= set(payload)


def test_research_universe_api_includes_user_assets():
    response = client.get("/api/research/universe")

    ids = {asset["asset_id"] for asset in response.json()["research_assets"]}
    assert {"H00300.CSI", "H20771.CSI", "801780.SI"} <= ids


def test_research_universe_api_marks_industry_monitor_assets_non_allocatable():
    response = client.get("/api/research/universe")

    industry_assets = [
        asset
        for asset in response.json()["research_assets"]
        if asset["category"] == "industry"
    ]
    assert len(industry_assets) == 18
    assert all(asset["role"] == "monitor" for asset in industry_assets)
    assert all(asset["eligible_for_allocation"] is False for asset in industry_assets)


def test_research_universe_api_returns_execution_proxy_mappings():
    response = client.get("/api/research/universe")

    mappings = {mapping["research_asset_id"]: mapping for mapping in response.json()["mappings"]}
    assert mappings["H00300.CSI"]["primary_execution_proxy"] == "510300.SH"
    assert mappings["H21152.CSI"]["primary_execution_proxy"] == "159992.SZ"
    assert mappings["H21152.CSI"]["mapping_quality"] == "high"


def test_research_universe_audit_api_returns_counts_and_warnings():
    response = client.get("/api/research/universe-audit")

    assert response.status_code == 200
    audit = response.json()["audit"]
    assert audit["research_asset_count"] == 33
    assert audit["execution_asset_count"] == 17
    assert audit["return_basis_counts"]["price_index"] == 18
    assert any("price_index" in warning for warning in audit["warnings"])
    assert audit["errors"] == []


def test_research_universe_page_returns_sections():
    response = client.get("/research-universe")

    assert response.status_code == 200
    assert "Research Universe" in response.text
    assert "Universe Audit" in response.text
    assert "Return Basis Counts" in response.text
    assert "Industry Monitor" in response.text
    assert "H00300.CSI" in response.text


def test_dashboard_links_research_universe_page():
    response = client.get("/research-universe")

    assert response.status_code == 200
    assert "Research Universe" in response.text
    assert "/research-universe" not in client.get("/").text
