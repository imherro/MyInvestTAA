from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from current_taa.drawdown_outcomes import HORIZONS
from current_taa.drawdown_threshold_cohorts import THRESHOLD_FAMILIES
from current_taa.drawdown_walk_forward_diagnostics import (
    DrawdownWalkForwardDiagnosticError,
    build_walk_forward_diagnostics,
    diagnose_walk_forward_ledger,
)
from scripts import build_a_tier_drawdown_walk_forward_diagnostics as builder
from scripts.build_a_tier_drawdown_walk_forward_diagnostics import (
    DrawdownWalkForwardDiagnosticBuildError,
    build_drawdown_walk_forward_diagnostic_report_set,
    publish_drawdown_walk_forward_diagnostic_report_set,
)
from scripts.build_a_tier_drawdown_walk_forward_evidence import (
    build_drawdown_walk_forward_evidence_report_set,
    publish_drawdown_walk_forward_evidence_report_set,
)
from tests.test_drawdown_walk_forward_evidence import _project_fixture, _report


def test_support_trajectories_and_prequential_diagnostics() -> None:
    body = diagnose_walk_forward_ledger(
        _ledger(), visible_series=_visible_series(900)
    )
    assert body["summary"] == {
        "threshold_group_count": 15,
        "event_evaluation_count": 4,
        "total_reached_evaluations": 15,
    }
    diagnostic = body["threshold_diagnostics"][0]
    assert diagnostic["status_support"] == {
        "event_evaluation_count": 4,
        "completed_test_event_count": 3,
        "open_test_event_count": 1,
        "insufficient_history_count": 1,
        "threshold_available_count": 3,
        "reached_count": 1,
        "not_reached_completed_count": 1,
        "not_reached_open_censored_count": 1,
    }
    support = diagnostic["training_support"][
        "coverage.threshold_available_event_count"
    ]
    assert support == {
        "defined_count": 4,
        "first_event_sequence": 1,
        "last_event_sequence": 4,
        "first_value": 0,
        "last_value": 3,
        "minimum": 0,
        "maximum": 3,
        "p50": 1.5,
    }
    depth = diagnostic["threshold_depth_stability"]
    assert depth["available_count"] == 3
    assert depth["adjacent_pair_count"] == 2
    assert depth["mean_absolute_step"] == pytest.approx(0.01)
    assert depth["mean_relative_step"] == pytest.approx(
        (0.01 / 0.1 + 0.01 / 0.11) / 2
    )

    metrics = diagnostic["training_metric_trajectories"]
    assert len(metrics) == 16
    attainment_metric = metrics[0]
    assert attainment_metric["defined_count"] == 3
    assert attainment_metric["null_count"] == 1
    assert attainment_metric["p50"] == 0.6
    assert attainment_metric["zero_crossing_count"] == 0

    attainment = diagnostic["attainment_prequential_diagnostic"]
    assert attainment["eligible_count"] == 2
    assert attainment["unresolved_open_count"] == 1
    assert attainment["positive_count"] == 1
    assert attainment["negative_count"] == 1
    assert attainment["mean_predicted_probability"] == pytest.approx(0.7)
    assert attainment["observed_frequency"] == 0.5
    assert attainment["calibration_gap"] == pytest.approx(-0.2)
    assert attainment["mean_absolute_calibration_gap"] == pytest.approx(0.2)
    assert attainment["brier_score"] == pytest.approx(0.2)

    recovery = diagnostic["trigger_recovery_prequential_diagnostics"][0]
    assert recovery["horizon_sessions"] == 63
    assert recovery["resolved_count"] == 1
    assert recovery["recovered_through_horizon_count"] == 1
    assert recovery["brier_score"] == pytest.approx(0.09)

    returns = diagnostic["forward_return_prequential_diagnostics"][0]
    assert returns["comparable_count"] == 1
    assert returns["mean_signed_error_vs_training_p50"] == pytest.approx(0.05)
    assert returns["mean_absolute_error_vs_training_p50"] == pytest.approx(0.05)
    assert returns["sign_agreement_rate"] == 1.0
    assert returns["inside_training_iqr_rate"] == 1.0


def test_recovery_censoring_and_null_prediction_semantics() -> None:
    ledger = _ledger()
    first_group = ledger["event_evaluations"][1]["threshold_evaluations"][0]
    first_group["test_outcome"]["trigger_price_recovery"] = {
        "status": "censored",
        "sessions_from_trigger": None,
    }
    diagnostic = diagnose_walk_forward_ledger(
        ledger, visible_series=_visible_series(150)
    )["threshold_diagnostics"][0]
    horizons = diagnostic["trigger_recovery_prequential_diagnostics"]
    assert horizons[0]["not_recovered_through_horizon_count"] == 0
    assert horizons[0]["unresolved_censored_count"] == 1

    ledger = _ledger()
    group = ledger["event_evaluations"][1]["training_snapshot"][
        "threshold_statistics"
    ][0]
    group["trigger_price_recovery"]["fixed_horizons"][0][
        "recovery_probability"
    ] = None
    diagnostic = diagnose_walk_forward_ledger(
        ledger, visible_series=_visible_series(900)
    )["threshold_diagnostics"][0]
    horizon = diagnostic["trigger_recovery_prequential_diagnostics"][0]
    assert horizon["predicted_unavailable_count"] == 1
    assert horizon["resolved_count"] == 0
    assert horizon["brier_score"] is None


def test_open_reached_and_recovery_horizon_resolution() -> None:
    ledger = _ledger()
    ledger["event_evaluations"][1]["event_completed_in_source"] = False
    attainment = diagnose_walk_forward_ledger(
        ledger, visible_series=_visible_series(900)
    )["threshold_diagnostics"][0]["attainment_prequential_diagnostic"]
    assert attainment["positive_count"] == 1
    assert attainment["eligible_count"] == 2

    ledger = _ledger()
    outcome = ledger["event_evaluations"][1]["threshold_evaluations"][0][
        "test_outcome"
    ]
    outcome["trigger_price_recovery"]["sessions_from_trigger"] = 64
    horizon = diagnose_walk_forward_ledger(
        ledger, visible_series=_visible_series(900)
    )["threshold_diagnostics"][0]["trigger_recovery_prequential_diagnostics"][0]
    assert horizon["resolved_count"] == 1
    assert horizon["not_recovered_through_horizon_count"] == 1

    ledger = _ledger()
    outcome = ledger["event_evaluations"][1]["threshold_evaluations"][0][
        "test_outcome"
    ]
    outcome["trigger_price_recovery"] = {
        "status": "censored",
        "sessions_from_trigger": None,
    }
    horizon = diagnose_walk_forward_ledger(
        ledger, visible_series=_visible_series(200)
    )["threshold_diagnostics"][0]["trigger_recovery_prequential_diagnostics"][0]
    assert horizon["resolved_count"] == 1
    assert horizon["not_recovered_through_horizon_count"] == 1
    assert [row["horizon_sessions"] for row in diagnose_walk_forward_ledger(
        ledger, visible_series=_visible_series(200)
    )["threshold_diagnostics"][0]["peak_recovery_prequential_diagnostics"]] == [
        63,
        126,
        252,
        504,
        756,
    ]


def test_forward_return_censoring_missing_distribution_and_zero_crossing() -> None:
    ledger = _ledger()
    evaluation = ledger["event_evaluations"][1]["threshold_evaluations"][0]
    evaluation["test_outcome"]["horizons"][0]["status"] = "censored"
    diagnostic = diagnose_walk_forward_ledger(
        ledger, visible_series=_visible_series(900)
    )["threshold_diagnostics"][0]
    first = diagnostic["forward_return_prequential_diagnostics"][0]
    assert first["test_window_censored_count"] == 1
    assert first["comparable_count"] == 0
    assert first["mean_absolute_error_vs_training_p50"] is None

    ledger = _ledger()
    training = ledger["event_evaluations"][1]["training_snapshot"][
        "threshold_statistics"
    ][0]
    training["horizon_outcomes"][0]["forward_return_distribution"][
        "p25"
    ] = None
    diagnostic = diagnose_walk_forward_ledger(
        ledger, visible_series=_visible_series(900)
    )["threshold_diagnostics"][0]
    assert diagnostic["forward_return_prequential_diagnostics"][0][
        "training_distribution_unavailable_count"
    ] == 1

    ledger = _ledger()
    metric_groups = [
        event["training_snapshot"]["threshold_statistics"][0]
        for event in ledger["event_evaluations"]
    ]
    for group, value in zip(metric_groups, (None, -0.1, 0.1, 0.0), strict=True):
        distribution = group["horizon_outcomes"][0][
            "forward_return_distribution"
        ]
        distribution["p50"] = value
        if value is not None:
            distribution["p25"] = value - 0.1
            distribution["p75"] = value + 0.1
    metrics = diagnose_walk_forward_ledger(
        ledger, visible_series=_visible_series(900)
    )["threshold_diagnostics"][0]["training_metric_trajectories"]
    assert metrics[-5]["zero_crossing_count"] == 1


def test_probability_bounds_and_empty_blocked_report() -> None:
    ledger = _ledger()
    ledger["event_evaluations"][1]["training_snapshot"][
        "threshold_statistics"
    ][0]["coverage"]["attainment_rate"] = 1.1
    with pytest.raises(
        DrawdownWalkForwardDiagnosticError, match="training metric is invalid"
    ):
        diagnose_walk_forward_ledger(
            ledger, visible_series=_visible_series(900)
        )
    assert build_walk_forward_diagnostics({"analysis_status": "blocked"}) == {
        "period": None,
        "summary": {
            "threshold_group_count": 0,
            "event_evaluation_count": 0,
            "total_reached_evaluations": 0,
        },
        "threshold_diagnostics": [],
    }


def test_as_of_equals_visible_prefix_and_ignores_future_fields() -> None:
    full = _report(100, 90, 100, 110, 99, 88, 110, 120, 60)
    as_of = build_walk_forward_diagnostics(full, as_of_date="2020-01-05")
    prefix = build_walk_forward_diagnostics(_report(100, 90, 100, 110, 99))
    assert as_of == prefix
    malformed = copy.deepcopy(full)
    malformed["drawdown_series"].append({"date": "bad", "close": "bad"})
    malformed["events"] = "future events"
    assert (
        build_walk_forward_diagnostics(
            malformed, as_of_date="2020-01-05"
        )
        == as_of
    )
    with pytest.raises(
        DrawdownWalkForwardDiagnosticError,
        match="actual input trading date",
    ):
        build_walk_forward_diagnostics(full, as_of_date="2030-01-01")


def test_builder_generates_exact_tier_a_reports_and_is_deterministic(
    tmp_path: Path,
) -> None:
    project = _complete_project(tmp_path)
    first = build_drawdown_walk_forward_diagnostic_report_set(
        project, generated_at="first"
    )
    second = build_drawdown_walk_forward_diagnostic_report_set(
        project, generated_at="second"
    )
    left = copy.deepcopy(first)
    right = copy.deepcopy(second)
    left["index.json"].pop("generated_at")
    right["index.json"].pop("generated_at")
    assert left == right
    assert first["index.json"]["summary"] == {
        "tier_a_assets": 7,
        "analyzed_assets": 5,
        "blocked_assets": 2,
        "threshold_groups_per_analyzed_asset": 15,
        "total_threshold_groups": 75,
        "total_event_evaluations": 5,
    }
    assert len(first) == 8
    assert "NaN" not in json.dumps(first, allow_nan=False)
    for report in first.values():
        assert "TUSHARE_TOKEN" not in json.dumps(report)


def test_builder_rejects_open_or_tampered_ledger_and_publishes_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _complete_project(tmp_path / "project")
    extra = (
        project
        / "reports/strategy_research/drawdown_walk_forward_evidence/extra.json"
    )
    extra.write_text("{}", encoding="utf-8")
    with pytest.raises(
        DrawdownWalkForwardDiagnosticBuildError,
        match="exactly the approved eight JSON files",
    ):
        build_drawdown_walk_forward_diagnostic_report_set(project)
    extra.unlink()

    ledger_path = (
        project
        / "reports/strategy_research/drawdown_walk_forward_evidence/csi300_total_return.json"
    )
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["event_evaluations"][0]["training_snapshot"][
        "threshold_statistics"
    ][0]["training_group_sha256"] = "0" * 64
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    with pytest.raises(
        DrawdownWalkForwardDiagnosticBuildError,
        match="business content",
    ):
        build_drawdown_walk_forward_diagnostic_report_set(project)

    reports = build_drawdown_walk_forward_diagnostic_report_set(
        _complete_project(tmp_path / "clean"), generated_at="fixed"
    )
    target = tmp_path / "published"
    target.mkdir()
    (target / "old.json").write_text("old", encoding="utf-8")
    original = builder._validate_stage

    def fail_stage(*_args) -> None:
        raise DrawdownWalkForwardDiagnosticBuildError("stage failure")

    monkeypatch.setattr(builder, "_validate_stage", fail_stage)
    with pytest.raises(
        DrawdownWalkForwardDiagnosticBuildError, match="stage failure"
    ):
        publish_drawdown_walk_forward_diagnostic_report_set(target, reports)
    assert (target / "old.json").read_text(encoding="utf-8") == "old"
    monkeypatch.setattr(builder, "_validate_stage", original)
    publish_drawdown_walk_forward_diagnostic_report_set(target, reports)
    assert {path.name for path in target.iterdir()} == set(reports)


def _complete_project(path: Path) -> Path:
    project = _project_fixture(path)
    ledgers = build_drawdown_walk_forward_evidence_report_set(
        project, generated_at="fixed"
    )
    publish_drawdown_walk_forward_evidence_report_set(
        project / "reports/strategy_research/drawdown_walk_forward_evidence",
        ledgers,
    )
    return project


def _ledger() -> dict:
    statuses = (
        ("insufficient_history", True, None),
        ("reached", True, _outcome()),
        ("not_reached", True, None),
        ("not_reached", False, None),
    )
    events = []
    for sequence, (status, completed, outcome) in enumerate(statuses, start=1):
        training = []
        evaluations = []
        for family, levels in THRESHOLD_FAMILIES:
            for level, probability in levels:
                training.append(_training_group(family, level, probability, sequence))
                evaluations.append(
                    {
                        "threshold_family": family,
                        "threshold_level": level,
                        "test_cohort": {
                            "threshold_status": status,
                            "threshold_depth": None if status == "insufficient_history" else 0.08 + 0.01 * sequence,
                        },
                        "test_outcome": copy.deepcopy(outcome),
                    }
                )
        events.append(
            {
                "event_sequence": sequence,
                "event_completed_in_source": completed,
                "training_snapshot": {"threshold_statistics": training},
                "threshold_evaluations": evaluations,
            }
        )
    return {
        "period": {"first_date": "d0", "last_date": "d899", "row_count": 900},
        "event_evaluations": events,
    }


def _training_group(family: str, level: str, probability: float, sequence: int) -> dict:
    attainment = (None, 0.8, 0.6, 0.5)[sequence - 1]
    fixed = [
        {
            "horizon_sessions": sessions,
            "label": label,
            "recovery_probability": None if sequence == 1 else 0.7,
        }
        for sessions, label in HORIZONS
    ]
    horizons = [
        {
            "horizon_sessions": sessions,
            "label": label,
            "observed_window_count": sequence - 1,
            "forward_return_distribution": {
                "p25": None if sequence == 1 else 0.0,
                "p50": None if sequence == 1 else 0.1,
                "p75": None if sequence == 1 else 0.2,
            },
        }
        for sessions, label in HORIZONS
    ]
    return {
        "threshold_family": family,
        "threshold_level": level,
        "threshold_probability_or_fraction": probability,
        "coverage": {
            "threshold_available_event_count": sequence - 1,
            "reached_event_count": max(0, sequence - 2),
            "attainment_rate": attainment,
        },
        "trigger_price_recovery": {"sample_count": max(0, sequence - 1), "fixed_horizons": copy.deepcopy(fixed)},
        "peak_recovery": {"sample_count": max(0, sequence - 1), "fixed_horizons": copy.deepcopy(fixed)},
        "horizon_outcomes": horizons,
    }


def _outcome() -> dict:
    return {
        "trigger_date": "d100",
        "trigger_price_recovery": {"status": "observed", "sessions_from_trigger": 50},
        "peak_recovery": {"status": "observed", "sessions_from_trigger": 70},
        "horizons": [
            {
                "horizon_sessions": sessions,
                "label": label,
                "status": "observed",
                "forward_return": 0.15,
            }
            for sessions, label in HORIZONS
        ],
    }


def _visible_series(count: int) -> list[dict]:
    return [{"date": f"d{index}", "close": 100.0} for index in range(count)]
