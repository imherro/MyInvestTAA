from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from current_taa.drawdown_events import analyze_drawdown_history
from current_taa.drawdown_threshold_statistics import build_threshold_statistics
from current_taa.drawdown_walk_forward_evidence import (
    DrawdownWalkForwardEvidenceError,
    _canonical_sha256,
    _test_outcome,
    build_walk_forward_evidence,
)
from scripts import build_a_tier_drawdown_walk_forward_evidence as ledger_builder
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
    build_drawdown_threshold_statistics_report_set,
    publish_drawdown_threshold_statistics_report_set,
)
from scripts.build_a_tier_drawdown_walk_forward_evidence import (
    DrawdownWalkForwardEvidenceBuildError,
    build_drawdown_walk_forward_evidence_report_set,
    publish_drawdown_walk_forward_evidence_report_set,
)


ROOT = Path(__file__).resolve().parents[1]
ANALYZED_KEYS = {
    "csi300_total_return",
    "csi500_total_return",
    "csi1000_total_return",
    "csi_dividend_total_return",
    "cni_free_cash_flow_total_return",
}


def test_each_event_uses_only_prior_events_for_training() -> None:
    body = build_walk_forward_evidence(
        _report(100, 90, 100, 110, 99, 110, 120, 60)
    )
    assert body["summary"]["event_count"] == 3
    assert body["summary"]["training_snapshot_count"] == 3
    assert body["summary"]["threshold_evaluation_count"] == 45
    for sequence, event in enumerate(body["event_evaluations"], start=1):
        snapshot = event["training_snapshot"]
        assert snapshot["prior_event_count"] == sequence - 1
        assert snapshot["threshold_group_count"] == 15
        assert len(snapshot["threshold_statistics"]) == 15
        assert len(event["threshold_evaluations"]) == 15
        assert {
            row["coverage"]["total_event_count"]
            for row in snapshot["threshold_statistics"]
        } == {sequence - 1}
    first = body["event_evaluations"][0]
    assert all(
        row["test_cohort"]["threshold_status"] == "insufficient_history"
        and row["test_outcome"] is None
        for row in first["threshold_evaluations"]
    )


def test_training_hash_binds_complete_as_of_statistics_group() -> None:
    report = _report(100, 90, 100, 110, 99)
    body = build_walk_forward_evidence(report)
    second = body["event_evaluations"][1]
    full_training = build_threshold_statistics(
        report, as_of_date=second["peak_date"]
    )
    compact = second["training_snapshot"]["threshold_statistics"][0]
    assert compact["training_group_sha256"] == _canonical_sha256(
        full_training["threshold_statistics"][0]
    )
    assert "samples" not in compact["trigger_price_recovery"]
    assert "timeline" not in compact["trigger_price_recovery"]
    assert "fixed_horizons" in compact["trigger_price_recovery"]


def test_current_and_future_results_do_not_change_prior_training_snapshot() -> None:
    base = build_walk_forward_evidence(_report(100, 90, 100, 110, 105))
    extended = build_walk_forward_evidence(
        _report(100, 90, 100, 110, 99, 55, 110, 120, 60, 120, 130, 65)
    )
    for event_index in (0, 1):
        assert base["event_evaluations"][event_index]["training_snapshot"] == (
            extended["event_evaluations"][event_index]["training_snapshot"]
        )
    base_second = base["event_evaluations"][1]["threshold_evaluations"]
    extended_second = extended["event_evaluations"][1]["threshold_evaluations"]
    assert [
        (
            row["test_cohort"]["threshold_depth"],
            row["test_cohort"]["sample_count"],
        )
        for row in base_second
    ] == [
        (
            row["test_cohort"]["threshold_depth"],
            row["test_cohort"]["sample_count"],
        )
        for row in extended_second
    ]


def test_reached_evaluation_links_outcome_and_open_result_is_censored() -> None:
    body = build_walk_forward_evidence(_report(100, 90, 100, 110, 99, 88))
    second = body["event_evaluations"][1]
    reached = [
        row
        for row in second["threshold_evaluations"]
        if row["test_cohort"]["threshold_status"] == "reached"
    ]
    assert reached
    for row in reached:
        assert row["test_outcome"]["record_id"] == row["test_cohort"][
            "selected_record_id"
        ]
        assert row["test_outcome"]["event_id"] == second["event_id"]
        assert row["test_outcome"]["peak_recovery"]["status"] == "censored"
        assert all(
            horizon["status"] == "censored"
            for horizon in row["test_outcome"]["horizons"]
        )


def test_non_reached_and_identity_errors_cannot_create_test_outcomes() -> None:
    cohort = {
        "threshold_status": "not_reached",
        "selected_record_id": None,
    }
    assert _test_outcome(cohort, {}) is None
    cohort["selected_record_id"] = "r"
    with pytest.raises(DrawdownWalkForwardEvidenceError, match="cannot select"):
        _test_outcome(cohort, {})

    reached = {
        "threshold_status": "reached",
        "selected_record_id": "r",
        "asset_key": "a",
        "event_id": "wrong",
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
    with pytest.raises(DrawdownWalkForwardEvidenceError, match="identity"):
        _test_outcome(reached, {"r": [record]})
    reached["event_id"] = "e"
    with pytest.raises(DrawdownWalkForwardEvidenceError, match="exactly one"):
        _test_outcome(reached, {"r": [record, record]})


def test_as_of_matches_prefix_and_ignores_malformed_future() -> None:
    full = _report(100, 90, 100, 110, 99, 88, 110, 120, 60)
    as_of = build_walk_forward_evidence(full, as_of_date="2020-01-05")
    prefix = build_walk_forward_evidence(_report(100, 90, 100, 110, 99))
    assert as_of == prefix
    assert len(as_of["event_evaluations"]) == 2
    assert as_of["event_evaluations"][-1]["event_completed_in_source"] is False

    malformed = copy.deepcopy(full)
    malformed["drawdown_series"].append({"date": "bad", "close": "bad"})
    malformed["events"] = "future events"
    malformed["current_state"] = "future current state"
    malformed["outcome_records"] = "future outcome"
    malformed["cohort_rows"] = "future cohort"
    malformed["statistics_rows"] = "future statistics"
    assert (
        build_walk_forward_evidence(malformed, as_of_date="2020-01-05")
        == as_of
    )
    malformed_visible = copy.deepcopy(full)
    malformed_visible["drawdown_series"][2]["close"] = "bad"
    with pytest.raises(DrawdownWalkForwardEvidenceError):
        build_walk_forward_evidence(
            malformed_visible, as_of_date="2020-01-05"
        )
    with pytest.raises(
        DrawdownWalkForwardEvidenceError,
        match="actual input trading date",
    ):
        build_walk_forward_evidence(full, as_of_date="2030-01-01")


def test_blocked_report_has_empty_ledger() -> None:
    body = build_walk_forward_evidence({"analysis_status": "blocked"})
    assert body == {
        "period": None,
        "summary": {
            "event_count": 0,
            "training_snapshot_count": 0,
            "threshold_evaluation_count": 0,
            "reached_count": 0,
            "not_reached_count": 0,
            "insufficient_history_count": 0,
        },
        "event_evaluations": [],
    }


def test_builder_generates_exact_tier_a_ledger_and_source_hashes(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    reports = build_drawdown_walk_forward_evidence_report_set(
        project, generated_at="fixed"
    )
    index = reports["index.json"]
    assert len(reports) == 8
    assert index["summary"] == {
        "tier_a_assets": 7,
        "analyzed_assets": 5,
        "blocked_assets": 2,
        "total_events": 5,
        "total_training_snapshots": 5,
        "total_threshold_evaluations": 75,
    }
    for source in ("event", "outcome", "cohort", "statistics"):
        path = project / index[f"source_{source}_index_path"]
        assert index[f"source_{source}_index_sha256"] == _sha256(path)
    for row in index["assets"]:
        report = reports[Path(row["report_path"]).name]
        if report["analysis_status"] == "analyzed":
            assert report["summary"]["threshold_evaluation_count"] == 15
            assert report["event_evaluations"][0]["training_snapshot"][
                "prior_event_count"
            ] == 0
        else:
            assert report["event_evaluations"] == []
            assert report["blockers"]


@pytest.mark.parametrize(
    "layer",
    [
        "drawdown_events",
        "drawdown_outcomes",
        "drawdown_threshold_cohorts",
        "drawdown_threshold_statistics",
    ],
)
def test_builder_rejects_open_source_sets(tmp_path: Path, layer: str) -> None:
    project = _project_fixture(tmp_path)
    path = project / f"reports/strategy_research/{layer}/extra.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(
        DrawdownWalkForwardEvidenceBuildError,
        match="exactly the approved eight JSON files",
    ):
        build_drawdown_walk_forward_evidence_report_set(project)


@pytest.mark.parametrize(
    "layer",
    [
        "drawdown_outcomes",
        "drawdown_threshold_cohorts",
        "drawdown_threshold_statistics",
    ],
)
def test_builder_rejects_tampered_business_content(
    tmp_path: Path, layer: str
) -> None:
    project = _project_fixture(tmp_path)
    path = project / f"reports/strategy_research/{layer}/csi300_total_return.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if layer == "drawdown_outcomes":
        report["records"][0]["trigger_depth"] = 0.999
    elif layer == "drawdown_threshold_cohorts":
        report["cohorts"][0]["threshold_status"] = "reached"
    else:
        report["threshold_statistics"][0]["coverage"][
            "total_event_count"
        ] = 99
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(
        DrawdownWalkForwardEvidenceBuildError, match="business content"
    ):
        build_drawdown_walk_forward_evidence_report_set(project)


def test_builder_is_deterministic_safe_and_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project_fixture(tmp_path / "project")
    first = build_drawdown_walk_forward_evidence_report_set(
        project, generated_at="first"
    )
    second = build_drawdown_walk_forward_evidence_report_set(
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
    original_validate = ledger_builder._validate_stage

    def fail_stage(*_args) -> None:
        raise DrawdownWalkForwardEvidenceBuildError("stage failure")

    monkeypatch.setattr(ledger_builder, "_validate_stage", fail_stage)
    with pytest.raises(DrawdownWalkForwardEvidenceBuildError, match="stage failure"):
        publish_drawdown_walk_forward_evidence_report_set(target, first)
    assert (target / "old.json").read_text(encoding="utf-8") == "old"

    monkeypatch.setattr(ledger_builder, "_validate_stage", original_validate)
    publish_drawdown_walk_forward_evidence_report_set(target, first)
    assert {path.name for path in target.glob("*.json")} == set(first)
    assert not (target / "old.json").exists()


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
    statistics = build_drawdown_threshold_statistics_report_set(
        tmp_path, generated_at="fixed"
    )
    publish_drawdown_threshold_statistics_report_set(
        tmp_path / "reports/strategy_research/drawdown_threshold_statistics",
        statistics,
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
