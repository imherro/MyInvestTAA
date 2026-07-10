import json

import pytest

from scripts.apply_research_universe_metadata import apply_research_universe_metadata


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _registry_rows():
    return [
        {
            "asset_id": "H00300.CSI",
            "name": "沪深300收益",
            "data_start_date": None,
            "investable_start_date": None,
            "eligible_for_allocation": True,
            "notes": "old",
        },
        {
            "asset_id": "399606.SZ",
            "name": "创业板R",
            "data_start_date": None,
            "investable_start_date": None,
            "eligible_for_allocation": True,
            "notes": "old manual note",
        },
        {
            "asset_id": "801780.SI",
            "name": "银行",
            "data_start_date": None,
            "investable_start_date": None,
            "eligible_for_allocation": False,
            "notes": "monitor",
        },
    ]


def _suggestion_report():
    return {
        "suggestions": [
            {
                "asset_id": "H00300.CSI",
                "data_start_date": "2016-01-04",
                "investable_start_date": "2016-01-04",
            },
            {
                "asset_id": "399606.SZ",
                "data_start_date": "2016-01-04",
                "investable_start_date": "2016-01-04",
            },
            {
                "asset_id": "801780.SI",
                "data_start_date": "2016-01-04",
                "investable_start_date": "2016-01-04",
            },
        ]
    }


def _fixture_paths(tmp_path):
    registry = tmp_path / "china_research_universe.json"
    suggestions = tmp_path / "suggestions.json"
    _write_json(registry, _registry_rows())
    _write_json(suggestions, _suggestion_report())
    return registry, suggestions


def test_apply_metadata_dry_run_does_not_write(tmp_path):
    registry, suggestions = _fixture_paths(tmp_path)

    summary = apply_research_universe_metadata(
        suggestions_path=suggestions,
        registry_path=registry,
        write=False,
    )
    rows = json.loads(registry.read_text(encoding="utf-8"))

    assert summary["mode"] == "dry_run"
    assert summary["applied_metadata_assets"] == 3
    assert rows[0]["data_start_date"] is None


def test_apply_metadata_write_updates_dates(tmp_path):
    registry, suggestions = _fixture_paths(tmp_path)

    summary = apply_research_universe_metadata(
        suggestions_path=suggestions,
        registry_path=registry,
        write=True,
    )
    rows = {row["asset_id"]: row for row in json.loads(registry.read_text(encoding="utf-8"))}

    assert summary["mode"] == "write"
    assert rows["H00300.CSI"]["data_start_date"] == "2016-01-04"
    assert rows["H00300.CSI"]["investable_start_date"] == "2016-01-04"


def test_apply_metadata_write_freezes_manual_review_asset(tmp_path):
    registry, suggestions = _fixture_paths(tmp_path)

    summary = apply_research_universe_metadata(
        suggestions_path=suggestions,
        registry_path=registry,
        write=True,
        freeze_manual_review_assets=True,
    )
    rows = {row["asset_id"]: row for row in json.loads(registry.read_text(encoding="utf-8"))}

    assert summary["frozen_manual_review_assets"] == 1
    assert rows["399606.SZ"]["eligible_for_allocation"] is False
    assert rows["399606.SZ"]["notes"] == "创业板R口径待人工确认；暂不进入主TAA配置"


def test_apply_metadata_without_freeze_keeps_allocation_flags(tmp_path):
    registry, suggestions = _fixture_paths(tmp_path)

    apply_research_universe_metadata(
        suggestions_path=suggestions,
        registry_path=registry,
        write=True,
        freeze_manual_review_assets=False,
    )
    rows = {row["asset_id"]: row for row in json.loads(registry.read_text(encoding="utf-8"))}

    assert rows["399606.SZ"]["eligible_for_allocation"] is True


def test_apply_metadata_keeps_price_index_monitor_ineligible(tmp_path):
    registry, suggestions = _fixture_paths(tmp_path)

    apply_research_universe_metadata(
        suggestions_path=suggestions,
        registry_path=registry,
        write=True,
        freeze_manual_review_assets=True,
    )
    rows = {row["asset_id"]: row for row in json.loads(registry.read_text(encoding="utf-8"))}

    assert rows["801780.SI"]["eligible_for_allocation"] is False


def test_apply_metadata_ignores_unknown_suggestions(tmp_path):
    registry, suggestions = _fixture_paths(tmp_path)
    report = _suggestion_report()
    report["suggestions"].append(
        {
            "asset_id": "UNKNOWN",
            "data_start_date": "2016-01-04",
            "investable_start_date": "2016-01-04",
        }
    )
    _write_json(suggestions, report)

    summary = apply_research_universe_metadata(
        suggestions_path=suggestions,
        registry_path=registry,
        write=True,
    )

    assert summary["suggestion_count"] == 4
    assert summary["changed_asset_count"] == 3


def test_apply_metadata_ignores_incomplete_suggestions(tmp_path):
    registry, suggestions = _fixture_paths(tmp_path)
    report = {
        "suggestions": [
            {
                "asset_id": "H00300.CSI",
                "data_start_date": "2016-01-04",
                "investable_start_date": None,
            }
        ]
    }
    _write_json(suggestions, report)

    summary = apply_research_universe_metadata(
        suggestions_path=suggestions,
        registry_path=registry,
        write=True,
    )

    assert summary["suggestion_count"] == 0
    assert summary["changed_asset_count"] == 0


@pytest.mark.parametrize("asset_id", ["H00300.CSI", "399606.SZ", "801780.SI"])
def test_apply_metadata_reports_asset_level_changes(asset_id, tmp_path):
    registry, suggestions = _fixture_paths(tmp_path)

    summary = apply_research_universe_metadata(
        suggestions_path=suggestions,
        registry_path=registry,
        write=False,
        freeze_manual_review_assets=True,
    )
    changes = {row["asset_id"]: row["changes"] for row in summary["changed_assets"]}

    assert asset_id in changes
    assert "data_start_date" in changes[asset_id]
