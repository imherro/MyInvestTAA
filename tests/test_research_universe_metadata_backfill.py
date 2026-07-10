from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import engine.asset_registry.metadata_backfill as metadata_backfill
from engine.asset_registry import (
    build_metadata_suggestions,
    build_research_data_availability_audit,
    build_research_universe_mock_provider,
    load_research_universe,
    write_metadata_suggestions,
)
from backend.main import app


client = TestClient(app)
RESEARCH_ASSETS = load_research_universe()
RESEARCH_ASSET_IDS = [asset.asset_id for asset in RESEARCH_ASSETS]


def _mock_audit_report(max_assets: int | None = None) -> dict:
    return build_research_data_availability_audit(
        build_research_universe_mock_provider(),
        max_assets=max_assets,
    )


def _unavailable_report(asset_id: str = "H00300.CSI") -> dict:
    report = _mock_audit_report(max_assets=2)
    for row in report["rows"]:
        if row["asset_id"] == asset_id:
            row["available"] = False
            row["row_count"] = 0
            row["first_date"] = None
            row["last_date"] = None
            row["error"] = "unit unavailable"
            row["warnings"] = ["data_unavailable"]
    report["available_assets"] = sum(1 for row in report["rows"] if row["available"])
    report["unavailable_assets"] = len(report["rows"]) - report["available_assets"]
    return report


def test_build_metadata_suggestions_counts_available_and_blocked_assets():
    report = _unavailable_report()

    suggestions = build_metadata_suggestions(report)

    assert suggestions["suggestion_count"] == 1
    assert suggestions["blocked_asset_count"] == 1
    assert suggestions["blocked_assets"][0]["asset_id"] == "H00300.CSI"


def test_build_metadata_suggestions_uses_tushare_source_name():
    report = _mock_audit_report(max_assets=1)
    report["provider"] = "tushare"

    suggestions = build_metadata_suggestions(report)

    assert suggestions["suggestions"][0]["source"] == "tushare_audit"


@pytest.mark.parametrize("asset_id", RESEARCH_ASSET_IDS)
def test_metadata_suggestions_include_each_available_asset(asset_id):
    report = _mock_audit_report()

    suggestions = build_metadata_suggestions(report)
    rows = {row["asset_id"]: row for row in suggestions["suggestions"]}

    assert rows[asset_id]["data_start_date"] == "2024-01-02"
    assert rows[asset_id]["investable_start_date"] == "2024-01-02"
    assert rows[asset_id]["last_date"] == "2024-12-31"
    assert rows[asset_id]["confidence"] == "high"


def test_metadata_suggestions_preserve_current_registry_dates():
    report = _mock_audit_report(max_assets=1)

    suggestions = build_metadata_suggestions(report)
    row = suggestions["suggestions"][0]

    assert row["current_data_start_date"] == "2016-01-04"
    assert row["current_investable_start_date"] == "2016-01-04"


def test_metadata_suggestions_skip_rows_without_dates():
    report = _mock_audit_report(max_assets=1)
    report["rows"][0]["first_date"] = None
    report["rows"][0]["last_date"] = None

    suggestions = build_metadata_suggestions(report)

    assert suggestions["suggestion_count"] == 0
    assert suggestions["blocked_asset_count"] == 1


def test_write_and_load_metadata_suggestions_report(tmp_path):
    path = tmp_path / "metadata.json"
    report = build_metadata_suggestions(_mock_audit_report(max_assets=1))

    written = write_metadata_suggestions(report, path)
    loaded = metadata_backfill.load_metadata_suggestions_report(path)

    assert written == path
    assert loaded["available"] is True
    assert loaded["suggestion_count"] == 1


def test_load_metadata_suggestions_missing_report(tmp_path):
    loaded = metadata_backfill.load_metadata_suggestions_report(tmp_path / "missing.json")

    assert loaded["available"] is False
    assert loaded["message"] == "research universe metadata suggestions report not found: missing.json"


def test_metadata_suggestions_api_missing_report(monkeypatch, tmp_path):
    monkeypatch.setattr(metadata_backfill, "RESEARCH_METADATA_SUGGESTIONS_REPORT", tmp_path / "missing.json")

    response = client.get("/api/research/universe-metadata-suggestions")

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_metadata_suggestions_api_existing_report(monkeypatch, tmp_path):
    path = tmp_path / "metadata.json"
    report = build_metadata_suggestions(_mock_audit_report(max_assets=2))
    write_metadata_suggestions(report, path)
    monkeypatch.setattr(metadata_backfill, "RESEARCH_METADATA_SUGGESTIONS_REPORT", path)

    response = client.get("/api/research/universe-metadata-suggestions")

    assert response.status_code == 200
    assert response.json()["suggestion_count"] == 2


def test_research_universe_page_displays_missing_metadata_report(monkeypatch, tmp_path):
    monkeypatch.setattr(metadata_backfill, "RESEARCH_METADATA_SUGGESTIONS_REPORT", tmp_path / "missing.json")

    response = client.get("/research-universe")

    assert response.status_code == 200
    assert "Metadata Suggestions" in response.text
    assert "research universe metadata suggestions report not found" in response.text


def test_research_universe_page_displays_metadata_suggestions(monkeypatch, tmp_path):
    path = tmp_path / "metadata.json"
    report = build_metadata_suggestions(_mock_audit_report(max_assets=1))
    write_metadata_suggestions(report, path)
    monkeypatch.setattr(metadata_backfill, "RESEARCH_METADATA_SUGGESTIONS_REPORT", path)

    response = client.get("/research-universe")

    assert response.status_code == 200
    assert "Metadata Suggestions" in response.text
    assert "H00300.CSI" in response.text


def test_metadata_suggestions_checked_in_report_placeholder_path_is_defined():
    assert Path("reports/research_universe_metadata_suggestions.json").exists()
