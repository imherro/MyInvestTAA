from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from current_taa.drawdown_events import analyze_drawdown_history
from current_taa.drawdown_outcomes import HORIZONS
from current_taa.drawdown_threshold_statistics import (
    DrawdownThresholdStatisticsError,
    _distribution,
    _first_median_recovery_time,
    _horizon_statistics,
    _kaplan_meier,
    _km_at_horizon,
    _minimum_statistics,
    _recovery_sample,
    _selected_record,
    _serialize_km_timeline,
    build_threshold_statistics,
)
from scripts import build_a_tier_drawdown_threshold_statistics as statistics_builder
from scripts.build_a_tier_drawdown_events import (
    build_drawdown_report_set,
    publish_drawdown_report_set,
)
from scripts.build_a_tier_drawdown_outcomes import (
    build_drawdown_outcome_report_set,
    publish_drawdown_outcome_report_set,
)
from scripts.build_a_tier_drawdown_threshold_cohorts import (
    build_drawdown_threshold_cohort_report_set,
    publish_drawdown_threshold_cohort_report_set,
)
from scripts.build_a_tier_drawdown_threshold_statistics import (
    DrawdownThresholdStatisticsBuildError,
    _validate_selected_links,
    build_drawdown_threshold_statistics_report_set,
    publish_drawdown_threshold_statistics_report_set,
)


ROOT = Path(__file__).resolve().parents[1]
ANALYZED_KEYS = {
    "csi300_total_return",
    "csi500_total_return",
    "csi1000_total_return",
    "csi_dividend_total_return",
    "cni_free_cash_flow_total_return",
}


def test_coverage_excludes_unavailable_and_not_reached_from_outcomes() -> None:
    body = build_threshold_statistics(_report(100, 50, 100, 110, 104.5))
    assert body["summary"] == {
        "threshold_group_count": 15,
        "total_event_count": 2,
        "total_reached_cohorts": 0,
    }
    for row in body["threshold_statistics"]:
        assert row["coverage"] == {
            "total_event_count": 2,
            "insufficient_history_count": 1,
            "threshold_available_event_count": 1,
            "reached_event_count": 0,
            "not_reached_event_count": 1,
            "attainment_rate": 0.0,
        }
        assert row["trigger_price_recovery"]["sample_count"] == 0
        assert row["peak_recovery"]["sample_count"] == 0
        assert all(
            horizon["survival_probability"] is None
            for horizon in row["trigger_price_recovery"]["fixed_horizons"]
        )

    unavailable = build_threshold_statistics(_report(100, 90))
    for row in unavailable["threshold_statistics"]:
        assert row["coverage"]["threshold_available_event_count"] == 0
        assert row["coverage"]["attainment_rate"] is None


def test_kaplan_meier_processes_recovery_before_same_time_censor() -> None:
    km = _kaplan_meier(
        [
            _sample("a", "observed", 1),
            _sample("b", "censored", 1),
            _sample("c", "observed", 2),
        ]
    )
    assert km["sample_count"] == 3
    assert km["observed_count"] == 2
    assert km["censored_count"] == 1
    assert km["naive_observed_fraction"] == 0.6666666667
    assert km["timeline"][0] == {
        "time_sessions": 1,
        "at_risk": 3,
        "observed_recoveries": 1,
        "censored": 1,
        "survival_probability": 0.6666666667,
        "recovery_probability": 0.3333333333,
        "greenwood_standard_error": 0.272165527,
    }
    assert km["timeline"][1]["at_risk"] == 1
    assert km["timeline"][1]["survival_probability"] == 0.0
    assert km["timeline"][1]["greenwood_standard_error"] == 0.0
    assert km["median_recovery_sessions"] == 2


def test_kaplan_meier_all_observed_all_censored_and_horizons() -> None:
    observed = _kaplan_meier(
        [_sample("a", "observed", 10), _sample("b", "observed", 10)]
    )
    assert observed["timeline"][0]["survival_probability"] == 0.0
    assert observed["median_recovery_sessions"] == 10

    censored = _kaplan_meier(
        [_sample("a", "censored", 20), _sample("b", "censored", 30)]
    )
    assert all(
        row["survival_probability"] == 1.0 for row in censored["timeline"]
    )
    assert censored["median_recovery_sessions"] is None

    mixed = _kaplan_meier(
        [
            _sample("a", "observed", 10),
            _sample("b", "censored", 100),
            _sample("c", "observed", 200),
        ]
    )
    h63, h126, h252 = mixed["fixed_horizons"][:3]
    assert h63["observed_recoveries_through_horizon"] == 1
    assert h63["censored_through_horizon"] == 0
    assert h63["recovery_probability"] == 0.3333333333
    assert h126["censored_through_horizon"] == 1
    assert h126["recovery_probability"] == 0.3333333333
    assert h252["observed_recoveries_through_horizon"] == 2
    assert h252["recovery_probability"] == 1.0


def test_km_median_uses_unrounded_survival_boundary() -> None:
    slightly_above = [
        _raw_km_row(10, 0.50000000004),
        _raw_km_row(20, 0.49),
    ]
    assert _serialize_km_timeline(slightly_above)[0][
        "survival_probability"
    ] == 0.5
    assert _first_median_recovery_time(slightly_above) == 20

    exact = [_raw_km_row(10, 0.5)]
    slightly_below = [_raw_km_row(10, 0.49999999996)]
    assert _first_median_recovery_time(exact) == 10
    assert _first_median_recovery_time(slightly_below) == 10
    assert _serialize_km_timeline(slightly_below)[0][
        "survival_probability"
    ] == 0.5


def test_km_fixed_horizon_serializes_unrounded_internal_state() -> None:
    raw_timeline = [
        _raw_km_row(10, 0.50000000004),
        _raw_km_row(20, 0.49),
    ]
    horizon = _km_at_horizon(
        [_sample("a", "censored", 100)], raw_timeline, 10, "boundary"
    )
    assert horizon["survival_probability"] == 0.5
    assert horizon["recovery_probability"] == 0.5
    assert _first_median_recovery_time(raw_timeline) == 20


def test_distributions_use_r7_and_distinguish_positive_from_nonnegative() -> None:
    distribution = _distribution([-1, 0, 1, 2], return_rates=True)
    assert distribution == {
        "sample_count": 4,
        "minimum": -1.0,
        "p25": -0.25,
        "p50": 0.5,
        "p75": 1.25,
        "maximum": 2.0,
        "mean": 0.5,
        "positive_count": 2,
        "positive_rate": 0.5,
        "non_negative_count": 3,
        "non_negative_rate": 0.75,
    }
    assert _distribution([])["mean"] is None


def test_open_event_recovery_censor_time_and_minimum_exclusion() -> None:
    body = build_threshold_statistics(_report(100, 90, 100, 110, 99, 88))
    fraction = _statistic(
        body,
        "historical_max_event_depth_fraction",
        "f50",
    )
    assert fraction["coverage"]["reached_event_count"] == 1
    trigger = fraction["trigger_price_recovery"]
    peak = fraction["peak_recovery"]
    assert trigger["observed_count"] == 0
    assert trigger["censored_count"] == 1
    assert trigger["samples"][0]["time_sessions"] == 1
    assert peak["samples"][0]["time_sessions"] == 1
    assert fraction["minimum_outcome"]["realized_count"] == 0
    assert fraction["minimum_outcome"]["censored_count"] == 1
    assert fraction["minimum_outcome"][
        "additional_return_distribution"
    ]["sample_count"] == 0


def test_fixed_window_and_realized_minimum_statistics() -> None:
    observed_horizon = {
        "horizon_sessions": 63,
        "label": "3m",
        "status": "observed",
        "forward_return": 0.1,
        "maximum_adverse_excursion": -0.2,
        "maximum_favorable_excursion": 0.3,
    }
    record = {
        "horizons": [
            observed_horizon,
            *[
                {
                    "horizon_sessions": sessions,
                    "label": label,
                    "status": "censored",
                    "forward_return": None,
                    "maximum_adverse_excursion": None,
                    "maximum_favorable_excursion": None,
                }
                for sessions, label in HORIZONS[1:]
            ],
        ],
        "minimum_outcome": {
            "status": "realized",
            "additional_return_from_trigger": -0.25,
            "sessions_from_trigger": 4,
        },
    }
    horizons = _horizon_statistics([record])
    assert horizons[0]["observed_window_count"] == 1
    assert horizons[0]["forward_return_distribution"]["positive_rate"] == 1.0
    assert horizons[0]["maximum_adverse_excursion_distribution"]["maximum"] <= 0
    assert horizons[0]["maximum_favorable_excursion_distribution"]["minimum"] >= 0
    assert horizons[1]["censored_window_count"] == 1
    assert horizons[1]["forward_return_distribution"]["sample_count"] == 0

    minimum = _minimum_statistics([record])
    assert minimum["realized_count"] == 1
    assert minimum["additional_return_distribution"]["p50"] == -0.25
    assert minimum["sessions_to_minimum_distribution"]["mean"] == 4.0


def test_completed_event_cannot_have_censored_recovery() -> None:
    cohort = {"cohort_id": "c", "event_id": "e"}
    record = {
        "record_id": "r",
        "event_id": "e",
        "trigger_date": "2020-01-01",
        "trigger_series_index": 0,
        "event_completed_in_source": True,
        "trigger_price_recovery": {
            "status": "censored",
            "sessions_from_trigger": None,
        },
    }
    with pytest.raises(
        DrawdownThresholdStatisticsError,
        match="completed event recovery cannot be censored",
    ):
        _recovery_sample(
            cohort,
            record,
            [{"date": "2020-01-01"}],
            "trigger_price_recovery",
        )


def test_selected_record_must_be_unique_and_identity_consistent() -> None:
    cohort = {
        "selected_record_id": "r",
        "asset_key": "a",
        "event_id": "e",
        "event_sequence": 1,
        "selected_frontier_sequence": 1,
        "trigger_date": "2020-01-02",
        "trigger_depth": 0.1,
        "trigger_drawdown": -0.1,
    }
    record = {
        "record_id": "r",
        "asset_key": "a",
        "event_id": "e",
        "event_sequence": 1,
        "frontier_sequence": 1,
        "trigger_date": "2020-01-02",
        "trigger_depth": 0.1,
        "trigger_drawdown": -0.1,
    }
    assert _selected_record(cohort, {"r": [record]}) == record
    with pytest.raises(DrawdownThresholdStatisticsError, match="exactly one"):
        _selected_record(cohort, {"r": [record, record]})
    changed = copy.deepcopy(cohort)
    changed["trigger_depth"] = 0.2
    with pytest.raises(DrawdownThresholdStatisticsError, match="identity"):
        _selected_record(changed, {"r": [record]})


def test_as_of_is_prefix_equivalent_and_future_invisible() -> None:
    full = _report(100, 90, 100, 110, 108, 99, 88, 110, 120, 60)
    as_of = build_threshold_statistics(full, as_of_date="2020-01-05")
    prefix = build_threshold_statistics(_report(100, 90, 100, 110, 108))
    assert as_of == prefix

    malformed = copy.deepcopy(full)
    malformed["drawdown_series"].append({"date": "bad", "close": "bad"})
    malformed["events"] = "future events"
    malformed["current_state"] = "future state"
    malformed["outcome_records"] = "future outcomes"
    malformed["cohort_rows"] = "future cohorts"
    assert (
        build_threshold_statistics(malformed, as_of_date="2020-01-05")
        == as_of
    )
    malformed_visible = copy.deepcopy(full)
    malformed_visible["drawdown_series"][2]["close"] = "bad"
    with pytest.raises(DrawdownThresholdStatisticsError):
        build_threshold_statistics(
            malformed_visible, as_of_date="2020-01-05"
        )
    with pytest.raises(
        DrawdownThresholdStatisticsError,
        match="actual input trading date",
    ):
        build_threshold_statistics(full, as_of_date="2030-01-01")


def test_blocked_report_has_empty_statistics() -> None:
    body = build_threshold_statistics({"analysis_status": "blocked"})
    assert body == {
        "period": None,
        "summary": {
            "threshold_group_count": 0,
            "total_event_count": 0,
            "total_reached_cohorts": 0,
        },
        "threshold_statistics": [],
    }


def test_builder_generates_exact_reports_and_source_hashes(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path)
    reports = build_drawdown_threshold_statistics_report_set(
        project, generated_at="fixed"
    )
    index = reports["index.json"]
    assert len(reports) == 8
    assert index["summary"] == {
        "tier_a_assets": 7,
        "analyzed_assets": 5,
        "blocked_assets": 2,
        "threshold_groups_per_analyzed_asset": 15,
        "total_threshold_groups": 75,
        "total_reached_cohorts": 0,
    }
    for source in ("event", "outcome", "cohort"):
        source_path = project / index[f"source_{source}_index_path"]
        assert index[f"source_{source}_index_sha256"] == _sha256(source_path)
    for row in index["assets"]:
        report = reports[Path(row["report_path"]).name]
        if report["analysis_status"] == "analyzed":
            assert len(report["threshold_statistics"]) == 15
        else:
            assert report["threshold_statistics"] == []
            assert report["blockers"]


@pytest.mark.parametrize(
    "layer",
    [
        "drawdown_events",
        "drawdown_outcomes",
        "drawdown_threshold_cohorts",
    ],
)
def test_builder_rejects_open_source_sets(tmp_path: Path, layer: str) -> None:
    project = _project_fixture(tmp_path)
    path = project / f"reports/strategy_research/{layer}/extra.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(
        DrawdownThresholdStatisticsBuildError,
        match="exactly the approved eight JSON files",
    ):
        build_drawdown_threshold_statistics_report_set(project)


@pytest.mark.parametrize(
    ("layer", "message"),
    [
        ("drawdown_outcomes", "outcome business content"),
        ("drawdown_threshold_cohorts", "cohort business content"),
    ],
)
def test_builder_rejects_tampered_business_content(
    tmp_path: Path, layer: str, message: str
) -> None:
    project = _project_fixture(tmp_path)
    path = project / f"reports/strategy_research/{layer}/csi300_total_return.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if layer == "drawdown_outcomes":
        report["records"][0]["trigger_depth"] = 0.999
    else:
        report["cohorts"][0]["threshold_status"] = "reached"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(DrawdownThresholdStatisticsBuildError, match=message):
        build_drawdown_threshold_statistics_report_set(project)


def test_builder_link_validation_rejects_missing_duplicate_and_mismatch() -> None:
    asset = type("Asset", (), {"asset_key": "a"})()
    record = {
        "record_id": "r",
        "asset_key": "a",
        "event_id": "e",
        "event_sequence": 1,
        "frontier_sequence": 1,
        "trigger_date": "2020-01-02",
        "trigger_depth": 0.1,
        "trigger_drawdown": -0.1,
    }
    outcome = {
        "analysis_status": "analyzed",
        "asset": {"asset_key": "a"},
        "records": [record],
    }
    cohort = {
        "analysis_status": "analyzed",
        "asset": {"asset_key": "a"},
        "cohorts": [
            {
                "threshold_status": "reached",
                "selected_record_id": "missing",
            }
        ],
    }
    with pytest.raises(DrawdownThresholdStatisticsBuildError, match="exactly one"):
        _validate_selected_links(asset, outcome, cohort)
    cohort["cohorts"][0] = {
        "threshold_status": "reached",
        "selected_record_id": "r",
        "asset_key": "a",
        "event_id": "other",
        "event_sequence": 1,
        "selected_frontier_sequence": 1,
        "trigger_date": "2020-01-02",
        "trigger_depth": 0.1,
        "trigger_drawdown": -0.1,
    }
    with pytest.raises(DrawdownThresholdStatisticsBuildError, match="identity"):
        _validate_selected_links(asset, outcome, cohort)
    outcome["records"].append(record)
    cohort["cohorts"][0]["event_id"] = "e"
    with pytest.raises(DrawdownThresholdStatisticsBuildError, match="exactly one"):
        _validate_selected_links(asset, outcome, cohort)


def test_builder_is_deterministic_safe_and_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project_fixture(tmp_path / "project")
    first = build_drawdown_threshold_statistics_report_set(
        project, generated_at="first"
    )
    second = build_drawdown_threshold_statistics_report_set(
        project, generated_at="second"
    )
    left = copy.deepcopy(first)
    right = copy.deepcopy(second)
    left["index.json"].pop("generated_at")
    right["index.json"].pop("generated_at")
    assert left == right
    serialized = json.dumps(first, allow_nan=False)
    assert "Infinity" not in serialized
    assert "TUSHARE_TOKEN" not in serialized

    target = tmp_path / "published"
    target.mkdir()
    (target / "old.json").write_text("old", encoding="utf-8")
    original_validate = statistics_builder._validate_stage

    def fail_stage(*_args) -> None:
        raise DrawdownThresholdStatisticsBuildError("stage failure")

    monkeypatch.setattr(statistics_builder, "_validate_stage", fail_stage)
    with pytest.raises(DrawdownThresholdStatisticsBuildError, match="stage failure"):
        publish_drawdown_threshold_statistics_report_set(target, first)
    assert (target / "old.json").read_text(encoding="utf-8") == "old"

    monkeypatch.setattr(statistics_builder, "_validate_stage", original_validate)
    publish_drawdown_threshold_statistics_report_set(target, first)
    assert {path.name for path in target.glob("*.json")} == set(first)
    assert not (target / "old.json").exists()


def _sample(identifier: str, status: str, sessions: int) -> dict:
    return {
        "cohort_id": identifier,
        "event_id": identifier,
        "selected_record_id": identifier,
        "trigger_date": "2020-01-01",
        "status": status,
        "time_sessions": sessions,
    }


def _raw_km_row(time_sessions: int, survival: float) -> dict:
    return {
        "time_sessions": time_sessions,
        "at_risk": 2,
        "observed_recoveries": 1,
        "censored": 0,
        "survival_probability": survival,
        "recovery_probability": 1 - survival,
        "greenwood_standard_error": 0.12345678904,
    }


def _statistic(body: dict, family: str, level: str) -> dict:
    return next(
        row
        for row in body["threshold_statistics"]
        if row["threshold_family"] == family and row["threshold_level"] == level
    )


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
        "drawdown_series": [point.to_dict() for point in analysis.drawdown_series],
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
    outcomes = build_drawdown_outcome_report_set(tmp_path, generated_at="fixed")
    publish_drawdown_outcome_report_set(
        tmp_path / "reports/strategy_research/drawdown_outcomes", outcomes
    )
    cohorts = build_drawdown_threshold_cohort_report_set(
        tmp_path, generated_at="fixed"
    )
    publish_drawdown_threshold_cohort_report_set(
        tmp_path / "reports/strategy_research/drawdown_threshold_cohorts",
        cohorts,
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
