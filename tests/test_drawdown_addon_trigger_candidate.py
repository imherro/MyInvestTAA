from __future__ import annotations

import copy
import json
import math
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_drawdown_addon_trigger_candidate import (  # noqa: E402
    SOURCE_RELATIVE,
    DrawdownAddonTriggerCandidateBuildError,
    build_drawdown_addon_trigger_candidate,
)


def _copy_source(tmp_path: Path) -> Path:
    target = tmp_path / SOURCE_RELATIVE
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / SOURCE_RELATIVE, target)
    return target


def _load_source(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_source(path: Path, source: dict) -> None:
    path.write_text(
        json.dumps(source, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _matching_source_row(source: dict, asset_key: str, level: str) -> dict:
    matches = [
        row
        for row in source["rows"]
        if row["asset_key"] == asset_key
        and row["threshold_family"] == "completed_event_depth_quantile"
        and row["threshold_level"] == level
    ]
    assert len(matches) == 1
    return matches[0]


def test_formal_candidate_has_fixed_family_levels_and_exact_evidence() -> None:
    source = json.loads((ROOT / SOURCE_RELATIVE).read_text(encoding="utf-8"))
    report = build_drawdown_addon_trigger_candidate(
        ROOT, generated_at="2026-07-16T00:00:00+00:00"
    )

    assert report["report_type"] == "a_tier_drawdown_addon_trigger_candidate"
    assert report["source_ledger_index_sha256"] == source["source_ledger_index_sha256"]
    assert report["rule"]["threshold_family"] == "completed_event_depth_quantile"
    assert report["rule"]["tiers"] == [
        {"tier": 1, "threshold_level": "p75"},
        {"tier": 2, "threshold_level": "p90"},
        {"tier": 3, "threshold_level": "p95"},
    ]
    assert len(report["assets"]) == 5
    assert sum(len(asset["tiers"]) for asset in report["assets"]) == 15
    assert len(report["blocked_assets"]) == 2
    assert all("tiers" not in asset for asset in report["blocked_assets"])

    for asset in report["assets"]:
        assert [tier["threshold_level"] for tier in asset["tiers"]] == [
            "p75",
            "p90",
            "p95",
        ]
        depths = [tier["current_reference_depth"] for tier in asset["tiers"]]
        assert depths[0] < depths[1] < depths[2]
        for tier in asset["tiers"]:
            row = _matching_source_row(
                source, asset["asset_key"], tier["threshold_level"]
            )
            assert tier["threshold_family"] == row["threshold_family"]
            assert tier["current_reference_depth"] == row["latest_threshold_depth"]
            assert tier["median_historical_depth"] == row["median_threshold_depth"]
            for field in (
                "reached_count",
                "resolved_attainment_count",
                "observed_attainment_rate",
                "one_year",
                "two_year",
                "post_trigger_additional_loss",
            ):
                assert tier[field] == row[field]


def test_missing_fixed_level_fails(tmp_path: Path) -> None:
    source_path = _copy_source(tmp_path)
    source = _load_source(source_path)
    source["rows"] = [
        row
        for row in source["rows"]
        if not (
            row["asset_key"] == "csi300_total_return"
            and row["threshold_family"] == "completed_event_depth_quantile"
            and row["threshold_level"] == "p90"
        )
    ]
    source["rows"].append(copy.deepcopy(source["rows"][0]))
    _write_source(source_path, source)

    with pytest.raises(
        DrawdownAddonTriggerCandidateBuildError, match="missing fixed trigger tier"
    ):
        build_drawdown_addon_trigger_candidate(tmp_path)


def test_non_increasing_current_depth_fails(tmp_path: Path) -> None:
    source_path = _copy_source(tmp_path)
    source = _load_source(source_path)
    p75 = _matching_source_row(source, "csi300_total_return", "p75")
    p90 = _matching_source_row(source, "csi300_total_return", "p90")
    p90["latest_threshold_depth"] = p75["latest_threshold_depth"]
    _write_source(source_path, source)

    with pytest.raises(
        DrawdownAddonTriggerCandidateBuildError, match="increase strictly"
    ):
        build_drawdown_addon_trigger_candidate(tmp_path)


def test_repeated_build_is_deterministic_except_generated_at() -> None:
    first = build_drawdown_addon_trigger_candidate(
        ROOT, generated_at="2026-07-16T00:00:00+00:00"
    )
    second = build_drawdown_addon_trigger_candidate(
        ROOT, generated_at="2026-07-17T00:00:00+00:00"
    )
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_formal_output_has_only_finite_numbers() -> None:
    report = build_drawdown_addon_trigger_candidate(ROOT)

    def assert_finite(value: object) -> None:
        if isinstance(value, float):
            assert math.isfinite(value)
        elif isinstance(value, dict):
            for nested in value.values():
                assert_finite(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_finite(nested)

    assert_finite(report)
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("report_type", "wrong_type", "source report type is invalid"),
        ("source_ledger_index_sha256", "", "source ledger index hash is required"),
    ],
)
def test_required_source_identity_fails(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    source_path = _copy_source(tmp_path)
    source = _load_source(source_path)
    source[field] = value
    _write_source(source_path, source)

    with pytest.raises(DrawdownAddonTriggerCandidateBuildError, match=message):
        build_drawdown_addon_trigger_candidate(tmp_path)
