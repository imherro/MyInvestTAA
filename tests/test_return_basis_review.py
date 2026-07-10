from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import engine.asset_registry.return_basis_review as return_basis_review
from engine.asset_registry import (
    build_research_data_availability_audit,
    build_research_universe_mock_provider,
    build_return_basis_review,
    load_research_universe,
    write_return_basis_review,
)
from backend.main import app


client = TestClient(app)
RESEARCH_ASSETS = load_research_universe()
TOTAL_RETURN_ASSET_IDS = [asset.asset_id for asset in RESEARCH_ASSETS if asset.return_basis == "total_return"]
PRICE_INDEX_ASSET_IDS = [asset.asset_id for asset in RESEARCH_ASSETS if asset.return_basis == "price_index"]


def _mock_audit_report(max_assets: int | None = None) -> dict:
    return build_research_data_availability_audit(
        build_research_universe_mock_provider(),
        max_assets=max_assets,
    )


def _row_ids(rows: list[dict]) -> set[str]:
    return {str(row["asset_id"]) for row in rows}


def test_return_basis_review_counts_mock_report_categories():
    review = build_return_basis_review(_mock_audit_report())

    assert len(review["registered_total_return_available"]) == 14
    assert len(review["basis_confirmed_total_return"]) == 14
    assert len(review["provider_metadata_mismatch"]) == 0
    assert len(review["needs_manual_review"]) == 1
    assert len(review["unavailable_total_return"]) == 0
    assert len(review["price_index_monitor_assets"]) == 18


@pytest.mark.parametrize("asset_id", TOTAL_RETURN_ASSET_IDS)
def test_return_basis_review_records_registered_total_return_available_assets(asset_id):
    review = build_return_basis_review(_mock_audit_report())

    assert asset_id in _row_ids(review["registered_total_return_available"])


@pytest.mark.parametrize("asset_id", TOTAL_RETURN_ASSET_IDS)
def test_return_basis_review_confirms_total_return_only_when_provider_marks_total_return(asset_id):
    review = build_return_basis_review(_mock_audit_report())

    assert asset_id in _row_ids(review["basis_confirmed_total_return"])


def test_return_basis_review_always_flags_399606_for_manual_review():
    review = build_return_basis_review(_mock_audit_report())
    manual = {row["asset_id"]: row for row in review["needs_manual_review"]}

    assert manual["399606.SZ"]["reason"] == "manual_return_basis_confirmation_required"


@pytest.mark.parametrize("asset_id", PRICE_INDEX_ASSET_IDS)
def test_return_basis_review_keeps_price_index_assets_as_monitor_only(asset_id):
    review = build_return_basis_review(_mock_audit_report())
    monitor_rows = {row["asset_id"]: row for row in review["price_index_monitor_assets"]}

    assert monitor_rows[asset_id]["return_basis"] == "price_index"
    assert monitor_rows[asset_id]["eligible_for_allocation"] is False
    assert monitor_rows[asset_id]["reason"] == "price_index_monitor_only"


def test_return_basis_review_records_unavailable_total_return_asset():
    report = _mock_audit_report(max_assets=1)
    report["rows"][0]["available"] = False
    report["rows"][0]["error"] = "unit unavailable"

    review = build_return_basis_review(report)

    assert review["unavailable_total_return"][0]["asset_id"] == "H00300.CSI"
    assert review["unavailable_total_return"][0]["reason"] == "unit unavailable"


def test_return_basis_review_records_provider_metadata_mismatch_for_price_marked_total_return():
    report = _mock_audit_report(max_assets=1)
    report["rows"][0]["provider_return_types"] = ["price"]

    review = build_return_basis_review(report)

    assert review["registered_total_return_available"][0]["asset_id"] == "H00300.CSI"
    assert review["basis_confirmed_total_return"] == []
    assert review["provider_metadata_mismatch"][0]["reason"] == "registry_declared_total_return_but_provider_marks_price"
    assert review["provider_metadata_mismatch"][0]["basis_confidence"] == "medium"


def test_return_basis_review_records_unknown_return_basis_for_manual_review():
    report = _mock_audit_report(max_assets=1)
    report["rows"][0]["return_basis"] = "mystery"

    review = build_return_basis_review(report)

    assert review["needs_manual_review"][0]["reason"] == "unknown_return_basis"


def test_return_basis_review_source_metadata():
    report = _mock_audit_report(max_assets=1)
    report["provider"] = "tushare"
    report["report_path"] = "reports/research_universe_data_audit_tushare.json"

    review = build_return_basis_review(report)

    assert review["source_report_provider"] == "tushare"
    assert review["source_report_path"] == "reports/research_universe_data_audit_tushare.json"


def test_write_and_load_return_basis_review_report(tmp_path):
    path = tmp_path / "review.json"
    report = build_return_basis_review(_mock_audit_report(max_assets=1))

    written = write_return_basis_review(report, path)
    loaded = return_basis_review.load_return_basis_review_report(path)

    assert written == path
    assert loaded["available"] is True
    assert loaded["report_path"] == str(path)
    assert "registered_total_return_available" in loaded


def test_load_return_basis_review_missing_report(tmp_path):
    loaded = return_basis_review.load_return_basis_review_report(tmp_path / "missing.json")

    assert loaded["available"] is False
    assert loaded["message"] == "research universe return basis review report not found: missing.json"


def test_return_basis_review_api_missing_report(monkeypatch, tmp_path):
    monkeypatch.setattr(return_basis_review, "RESEARCH_RETURN_BASIS_REVIEW_REPORT", tmp_path / "missing.json")

    response = client.get("/api/research/return-basis-review")

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_return_basis_review_api_existing_report(monkeypatch, tmp_path):
    path = tmp_path / "review.json"
    report = build_return_basis_review(_mock_audit_report(max_assets=1))
    write_return_basis_review(report, path)
    monkeypatch.setattr(return_basis_review, "RESEARCH_RETURN_BASIS_REVIEW_REPORT", path)

    response = client.get("/api/research/return-basis-review")

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert "registered_total_return_available" in response.json()


def test_research_universe_page_displays_missing_return_basis_report(monkeypatch, tmp_path):
    monkeypatch.setattr(return_basis_review, "RESEARCH_RETURN_BASIS_REVIEW_REPORT", tmp_path / "missing.json")

    response = client.get("/research-universe")

    assert response.status_code == 200
    assert "Return Basis Review" in response.text
    assert "research universe return basis review report not found" in response.text


def test_research_universe_page_displays_return_basis_review(monkeypatch, tmp_path):
    path = tmp_path / "review.json"
    report = build_return_basis_review(_mock_audit_report())
    write_return_basis_review(report, path)
    monkeypatch.setattr(return_basis_review, "RESEARCH_RETURN_BASIS_REVIEW_REPORT", path)

    response = client.get("/research-universe")

    assert response.status_code == 200
    assert "Manual Return Basis Review" in response.text
    assert "399606.SZ" in response.text


def test_return_basis_checked_in_report_placeholder_path_is_defined():
    assert Path("reports/research_universe_return_basis_review.json").exists()
