from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import pytest

from scripts.build_a_tier_drawdown_threshold_evidence_table import (
    LEDGER_RELATIVE,
    DrawdownThresholdEvidenceTableBuildError,
    _summarize_group,
    build_drawdown_threshold_evidence_table,
)


ROOT = Path(__file__).resolve().parents[1]


def test_formal_table_has_fixed_rows_order_and_ledger_identity() -> None:
    report = build_drawdown_threshold_evidence_table(ROOT, generated_at="2026-07-16T00:00:00+00:00")
    index_bytes = (ROOT / LEDGER_RELATIVE / "index.json").read_bytes()
    ledger = json.loads(index_bytes)

    assert report["source_ledger_index_sha256"] == hashlib.sha256(index_bytes).hexdigest()
    assert report["summary"] == {
        "tier_a_assets": 7,
        "analyzed_assets": 5,
        "blocked_assets": 2,
        "threshold_rows": 75,
    }
    assert len(report["rows"]) == 75
    assert [entry["asset_key"] for entry in report["blocked_assets"]] == [
        asset["asset_key"] for asset in ledger["assets"] if asset["analysis_status"] == "blocked"
    ]
    analyzed = [asset for asset in ledger["assets"] if asset["analysis_status"] == "analyzed"]
    assert [row["asset_key"] for row in report["rows"]] == [
        asset["asset_key"] for asset in analyzed for _ in range(15)
    ]
    group_order = [
        (row["threshold_family"], row["threshold_level"])
        for row in report["rows"][:15]
    ]
    assert all(
        [(row["threshold_family"], row["threshold_level"]) for row in report["rows"][offset:offset + 15]]
        == group_order
        for offset in range(0, 75, 15)
    )
    _assert_finite(report)


def test_group_summary_separates_open_censored_and_zero_returns() -> None:
    asset = {"asset_key": "asset", "display_name": "Asset", "risk_family": "family"}
    entries = [
        _entry("insufficient_history", True, 0.10),
        _entry("not_reached", False, 0.20),
        _entry("not_reached", True, 0.30),
        _entry("reached", True, 0.40, one_year=("observed", 0.10), two_year=("observed", 0.0), minimum=("realized", -0.20)),
        _entry("reached", False, 0.80, one_year=("censored", None), two_year=("censored", None), minimum=("censored", None)),
    ]

    row = _summarize_group(asset, "family", "p75", entries)

    assert row["event_count"] == 5
    assert row["insufficient_history_count"] == 1
    assert row["reached_count"] == 2
    assert row["completed_not_reached_count"] == 1
    assert row["open_not_reached_unresolved_count"] == 1
    assert row["resolved_attainment_count"] == 3
    assert row["observed_attainment_rate"] == pytest.approx(2 / 3)
    assert row["latest_threshold_depth"] == 0.80
    assert row["median_threshold_depth"] == 0.30
    assert row["one_year"] == {
        "reached_count": 2,
        "observed_count": 1,
        "censored_count": 1,
        "median_forward_return": 0.10,
        "positive_return_count": 1,
        "positive_return_rate": 1.0,
    }
    assert row["two_year"]["positive_return_count"] == 0
    assert row["two_year"]["positive_return_rate"] == 0.0
    assert row["post_trigger_additional_loss"] == {
        "reached_count": 2,
        "realized_count": 1,
        "censored_count": 1,
        "median_additional_loss": 0.20,
        "p75_additional_loss": 0.20,
    }


def test_group_summary_uses_r7_for_returns_and_additional_loss() -> None:
    asset = {"asset_key": "asset", "display_name": "Asset", "risk_family": "family"}
    entries = [
        _entry("reached", True, depth, one_year=("observed", value), two_year=("observed", value), minimum=("realized", -value))
        for depth, value in ((0.1, 0.1), (0.2, 0.2), (0.4, 0.4), (0.8, 0.8))
    ]

    row = _summarize_group(asset, "family", "p75", entries)

    assert row["median_threshold_depth"] == pytest.approx(0.3)
    assert row["one_year"]["median_forward_return"] == pytest.approx(0.3)
    assert row["post_trigger_additional_loss"]["median_additional_loss"] == pytest.approx(0.3)
    assert row["post_trigger_additional_loss"]["p75_additional_loss"] == pytest.approx(0.5)


def test_builder_rejects_missing_outcome_for_reached_event(tmp_path: Path) -> None:
    _copy_ledger(tmp_path)
    target = tmp_path / LEDGER_RELATIVE / "csi300_total_return.json"
    report = json.loads(target.read_text(encoding="utf-8"))
    reached = next(
        evaluation
        for event in report["event_evaluations"]
        for evaluation in event["threshold_evaluations"]
        if evaluation["test_cohort"]["threshold_status"] == "reached"
    )
    reached["test_outcome"] = None
    target.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(DrawdownThresholdEvidenceTableBuildError, match="outcome state"):
        build_drawdown_threshold_evidence_table(tmp_path)


def test_repeated_builds_are_equal_except_generated_at() -> None:
    first = build_drawdown_threshold_evidence_table(ROOT, generated_at="2026-07-16T00:00:00+00:00")
    second = build_drawdown_threshold_evidence_table(ROOT, generated_at="2026-07-17T00:00:00+00:00")
    assert {key: value for key, value in first.items() if key != "generated_at"} == {
        key: value for key, value in second.items() if key != "generated_at"
    }


def _entry(
    status: str,
    completed: bool,
    depth: float,
    *,
    one_year: tuple[str, float | None] | None = None,
    two_year: tuple[str, float | None] | None = None,
    minimum: tuple[str, float | None] | None = None,
) -> dict[str, object]:
    evaluation: dict[str, object] = {
        "threshold_probability_or_fraction": 0.75,
        "test_cohort": {"threshold_status": status, "threshold_depth": depth},
        "test_outcome": None,
    }
    if status == "reached":
        assert one_year is not None and two_year is not None and minimum is not None
        evaluation["test_outcome"] = {
            "horizons": [
                {"horizon_sessions": 252, "status": one_year[0], "forward_return": one_year[1]},
                {"horizon_sessions": 504, "status": two_year[0], "forward_return": two_year[1]},
            ],
            "minimum_outcome": {
                "status": minimum[0],
                "additional_return_from_trigger": minimum[1],
            },
        }
    return {"event": {"event_completed_in_source": completed}, "evaluation": evaluation}


def _copy_ledger(target_root: Path) -> None:
    source = ROOT / LEDGER_RELATIVE
    target = target_root / LEDGER_RELATIVE
    target.mkdir(parents=True)
    for path in source.iterdir():
        target.joinpath(path.name).write_bytes(path.read_bytes())


def _assert_finite(value: object) -> None:
    if isinstance(value, float):
        assert math.isfinite(value)
    elif isinstance(value, dict):
        for nested in value.values():
            _assert_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_finite(nested)
