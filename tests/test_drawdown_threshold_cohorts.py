from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from current_taa.drawdown_events import analyze_drawdown_history
from current_taa.drawdown_threshold_cohorts import (
    DrawdownThresholdCohortError,
    THRESHOLD_FAMILIES,
    build_threshold_cohorts,
)
from scripts import build_a_tier_drawdown_threshold_cohorts as cohort_builder
from scripts.build_a_tier_drawdown_events import (
    build_drawdown_report_set,
    publish_drawdown_report_set,
)
from scripts.build_a_tier_drawdown_outcomes import (
    build_drawdown_outcome_report_set,
    publish_drawdown_outcome_report_set,
)
from scripts.build_a_tier_drawdown_threshold_cohorts import (
    DrawdownThresholdCohortBuildError,
    build_drawdown_threshold_cohort_report_set,
    publish_drawdown_threshold_cohort_report_set,
)


ROOT = Path(__file__).resolve().parents[1]
ANALYZED_KEYS = {
    "csi300_total_return",
    "csi500_total_return",
    "csi1000_total_return",
    "csi_dividend_total_return",
    "cni_free_cash_flow_total_return",
}


def test_thresholds_are_frozen_at_event_peak_and_use_only_prior_history() -> None:
    report = _report(100, 90, 80, 100, 110, 99, 88, 110, 120, 60)
    body = build_threshold_cohorts(report)
    second = _event_rows(body, 2)
    daily = _family_rows(second, "underwater_daily_depth_quantile")
    completed = _family_rows(second, "completed_event_depth_quantile")
    fractions = _family_rows(second, "historical_max_event_depth_fraction")

    assert [row["threshold_depth"] for row in daily] == [
        0.175,
        0.18,
        0.185,
        0.19,
        0.195,
    ]
    assert {row["sample_count"] for row in daily} == {2}
    assert {row["sample_end_date"] for row in daily} == {"2020-01-03"}
    assert [row["threshold_depth"] for row in completed] == [0.2] * 5
    assert {row["completed_event_sample_count"] for row in completed} == {1}
    assert [row["threshold_depth"] for row in fractions] == [
        0.1,
        0.12,
        0.14,
        0.16,
        0.18,
    ]
    assert {row["estimation_cutoff_date"] for row in second} == {
        "2020-01-05"
    }

    deeper_future = _report(
        100, 90, 80, 100, 110, 99, 88, 55, 110, 120, 60, 120, 130, 65
    )
    assert _threshold_facts(_event_rows(build_threshold_cohorts(deeper_future), 2)) == (
        _threshold_facts(second)
    )


def test_empty_and_single_value_samples_follow_contract() -> None:
    body = build_threshold_cohorts(_report(100, 90, 100, 110, 99))
    first = _event_rows(body, 1)
    assert len(first) == 15
    assert {row["threshold_status"] for row in first} == {
        "insufficient_history"
    }
    assert all(row["threshold_depth"] is None for row in first)

    second = _event_rows(body, 2)
    assert [
        row["threshold_depth"]
        for row in _family_rows(second, "underwater_daily_depth_quantile")
    ] == [0.1] * 5
    assert [
        row["threshold_depth"]
        for row in _family_rows(second, "completed_event_depth_quantile")
    ] == [0.1] * 5


def test_first_crossing_equality_deduplication_and_not_reached() -> None:
    body = build_threshold_cohorts(
        _report(100, 90, 80, 100, 110, 99, 88, 110)
    )
    second = _event_rows(body, 2)
    fractions = _family_rows(second, "historical_max_event_depth_fraction")
    assert fractions[0]["threshold_depth"] == 0.1
    assert fractions[0]["trigger_depth"] == 0.1
    assert fractions[0]["selected_frontier_sequence"] == 1
    assert fractions[1]["selected_frontier_sequence"] == 2
    assert all(row["threshold_status"] == "reached" for row in fractions)
    assert len({row["cohort_id"] for row in second}) == 15

    shallow = build_threshold_cohorts(_report(100, 50, 100, 110, 104.5))
    completed = _family_rows(
        _event_rows(shallow, 2), "completed_event_depth_quantile"
    )
    assert all(row["threshold_status"] == "not_reached" for row in completed)
    assert all(row["selected_record_id"] is None for row in completed)


def test_cohort_order_ids_and_family_counts_are_stable() -> None:
    body = build_threshold_cohorts(_report(100, 90, 100, 110, 99))
    expected = []
    for event_sequence in (1, 2):
        for family, levels in THRESHOLD_FAMILIES:
            expected.extend(
                (event_sequence, family, level) for level, _ in levels
            )
    actual = [
        (row["event_sequence"], row["threshold_family"], row["threshold_level"])
        for row in body["cohorts"]
    ]
    assert actual == expected
    assert body["summary"]["candidate_threshold_count"] == 30
    for row in body["cohorts"]:
        assert row["cohort_id"] == (
            f"asset:{row['event_sequence']}:"
            f"{row['threshold_family']}:{row['threshold_level']}"
        )


def test_as_of_matches_visible_prefix_and_hides_future_crossings() -> None:
    full = _report(100, 90, 100, 110, 108, 99, 88, 110, 120, 60)
    as_of = build_threshold_cohorts(full, as_of_date="2020-01-05")
    prefix = build_threshold_cohorts(_report(100, 90, 100, 110, 108))
    assert as_of == prefix
    second = _event_rows(as_of, 2)
    assert all(
        row["threshold_status"] == "not_reached"
        for row in second
        if row["threshold_depth"] is not None
        and row["threshold_depth"] > 0.0181818182
    )


def test_as_of_ignores_malformed_future_and_rejects_visible_errors() -> None:
    report = _report(100, 90, 100, 110, 99)
    expected = build_threshold_cohorts(report, as_of_date="2020-01-04")
    malformed_future = copy.deepcopy(report)
    malformed_future["drawdown_series"].append(
        {"date": "not-a-date", "close": "bad"}
    )
    malformed_future["events"] = "future facts must not be read"
    assert (
        build_threshold_cohorts(
            malformed_future, as_of_date="2020-01-04"
        )
        == expected
    )

    malformed_visible = copy.deepcopy(report)
    malformed_visible["drawdown_series"][2]["close"] = "bad"
    with pytest.raises(DrawdownThresholdCohortError):
        build_threshold_cohorts(
            malformed_visible, as_of_date="2020-01-04"
        )
    with pytest.raises(
        DrawdownThresholdCohortError,
        match="actual input trading date",
    ):
        build_threshold_cohorts(report, as_of_date="2020-02-01")


def test_blocked_report_has_empty_cohorts() -> None:
    body = build_threshold_cohorts(
        {"analysis_status": "blocked", "asset": {"asset_key": "blocked"}}
    )
    assert body == {
        "period": None,
        "summary": {
            "event_count": 0,
            "candidate_threshold_count": 0,
            "reached_count": 0,
            "not_reached_count": 0,
            "insufficient_history_count": 0,
        },
        "cohorts": [],
    }


def test_builder_generates_exact_tier_a_set_and_source_hashes(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    reports = build_drawdown_threshold_cohort_report_set(
        project, generated_at="fixed"
    )
    index = reports["index.json"]
    assert len(reports) == 8
    assert index["summary"] == {
        "tier_a_assets": 7,
        "analyzed_assets": 5,
        "blocked_assets": 2,
        "total_events": 5,
        "total_candidate_thresholds": 75,
        "total_reached": 0,
        "total_not_reached": 0,
        "total_insufficient_history": 75,
    }
    assert [row["analysis_status"] for row in index["assets"]].count(
        "analyzed"
    ) == 5
    assert index["source_event_index_sha256"] == _sha256(
        project / "reports/strategy_research/drawdown_events/index.json"
    )
    assert index["source_outcome_index_sha256"] == _sha256(
        project / "reports/strategy_research/drawdown_outcomes/index.json"
    )
    for row in index["assets"]:
        report = reports[Path(row["report_path"]).name]
        if report["analysis_status"] == "analyzed":
            assert report["summary"]["candidate_threshold_count"] == 15
        else:
            assert report["period"] is None
            assert report["cohorts"] == []
            assert report["blockers"]


@pytest.mark.parametrize(
    "relative",
    [
        "reports/strategy_research/drawdown_events/extra.json",
        "reports/strategy_research/drawdown_outcomes/extra.json",
    ],
)
def test_builder_rejects_open_source_json_sets(
    tmp_path: Path, relative: str
) -> None:
    project = _project_fixture(tmp_path)
    path = project / relative
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(
        DrawdownThresholdCohortBuildError,
        match="exactly the approved eight JSON files",
    ):
        build_drawdown_threshold_cohort_report_set(project)


def test_builder_rejects_tampered_outcome_business_content(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    path = (
        project
        / "reports/strategy_research/drawdown_outcomes/csi300_total_return.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))
    report["records"][0]["trigger_depth"] = 0.999
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(
        DrawdownThresholdCohortBuildError,
        match="business content differs",
    ):
        build_drawdown_threshold_cohort_report_set(project)


def test_builder_is_deterministic_safe_and_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project_fixture(tmp_path / "project")
    first = build_drawdown_threshold_cohort_report_set(
        project, generated_at="first"
    )
    second = build_drawdown_threshold_cohort_report_set(
        project, generated_at="second"
    )
    first_without_time = copy.deepcopy(first)
    second_without_time = copy.deepcopy(second)
    first_without_time["index.json"].pop("generated_at")
    second_without_time["index.json"].pop("generated_at")
    assert first_without_time == second_without_time
    serialized = json.dumps(first, allow_nan=False)
    assert "Infinity" not in serialized
    assert "TUSHARE_TOKEN" not in serialized

    target = tmp_path / "published"
    target.mkdir()
    (target / "old.json").write_text("old", encoding="utf-8")
    original_validate = cohort_builder._validate_stage

    def fail_stage(*_args) -> None:
        raise DrawdownThresholdCohortBuildError("stage failure")

    monkeypatch.setattr(cohort_builder, "_validate_stage", fail_stage)
    with pytest.raises(DrawdownThresholdCohortBuildError, match="stage failure"):
        publish_drawdown_threshold_cohort_report_set(target, first)
    assert (target / "old.json").read_text(encoding="utf-8") == "old"

    monkeypatch.setattr(cohort_builder, "_validate_stage", original_validate)
    publish_drawdown_threshold_cohort_report_set(target, first)
    assert {path.name for path in target.glob("*.json")} == set(first)
    assert not (target / "old.json").exists()


def _event_rows(body: dict, sequence: int) -> list[dict]:
    return [
        row for row in body["cohorts"] if row["event_sequence"] == sequence
    ]


def _family_rows(rows: list[dict], family: str) -> list[dict]:
    return [row for row in rows if row["threshold_family"] == family]


def _threshold_facts(rows: list[dict]) -> list[tuple]:
    return [
        (
            row["threshold_family"],
            row["threshold_level"],
            row["threshold_depth"],
            row["sample_count"],
            row["sample_start_date"],
            row["sample_end_date"],
        )
        for row in rows
    ]


def _report(*prices: float) -> dict:
    analysis = analyze_drawdown_history(_rows(*prices), asset_key="asset")
    events = [event.to_dict() for event in analysis.events]
    return {
        "analysis_status": "analyzed",
        "asset": {
            "asset_key": "asset",
            "provider_code": "p",
            "risk_family": "broad_beta",
        },
        "period": {
            "first_date": analysis.first_date,
            "last_date": analysis.last_date,
            "row_count": analysis.row_count,
        },
        "event_summary": {
            "total_event_count": len(events),
            "completed_event_count": sum(event["completed"] for event in events),
            "open_event_count": sum(not event["completed"] for event in events),
        },
        "events": events,
        "drawdown_series": [
            point.to_dict() for point in analysis.drawdown_series
        ],
        "current_state": analysis.current_state,
    }


def _project_fixture(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "reports/strategy_research").mkdir(parents=True)
    (tmp_path / "data/research_prices").mkdir(parents=True)
    (tmp_path / "config/research_universe_v1.json").write_bytes(
        (ROOT / "config/research_universe_v1.json").read_bytes()
    )
    (tmp_path / "reports/strategy_research/universe_audit.json").write_bytes(
        (ROOT / "reports/strategy_research/universe_audit.json").read_bytes()
    )
    contract = json.loads(
        (tmp_path / "config/research_universe_v1.json").read_text(
            encoding="utf-8"
        )
    )
    for asset in contract["assets"][:7]:
        if asset["asset_key"] in ANALYZED_KEYS:
            path = (
                tmp_path
                / "data/research_prices"
                / f"{asset['provider_code'].replace('.', '_')}.json"
            )
            path.write_text(
                json.dumps(_rows(100, 90, 80, 100)), encoding="utf-8"
            )
    events = build_drawdown_report_set(tmp_path, generated_at="fixed")
    publish_drawdown_report_set(
        tmp_path / "reports/strategy_research/drawdown_events", events
    )
    outcomes = build_drawdown_outcome_report_set(
        tmp_path, generated_at="fixed"
    )
    publish_drawdown_outcome_report_set(
        tmp_path / "reports/strategy_research/drawdown_outcomes", outcomes
    )
    return tmp_path


def _rows(*prices: float) -> list[dict]:
    start = date(2020, 1, 1)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "close": price,
            "return_basis": "total_return",
        }
        for index, price in enumerate(prices)
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
