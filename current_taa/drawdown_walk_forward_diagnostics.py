from __future__ import annotations

import math
from typing import Any, Callable

from current_taa.drawdown_outcomes import HORIZONS
from current_taa.drawdown_profiles import linear_quantile
from current_taa.drawdown_threshold_cohorts import THRESHOLD_FAMILIES
from current_taa.drawdown_walk_forward_evidence import build_walk_forward_evidence


class DrawdownWalkForwardDiagnosticError(ValueError):
    pass


def build_walk_forward_diagnostics(
    asset_event_report: dict[str, Any], *, as_of_date: str | None = None
) -> dict[str, Any]:
    try:
        ledger = build_walk_forward_evidence(
            asset_event_report, as_of_date=as_of_date
        )
        if asset_event_report.get("analysis_status") == "blocked":
            return {
                "period": None,
                "summary": _summary([]),
                "threshold_diagnostics": [],
            }
        visible_series = _visible_series(
            asset_event_report.get("drawdown_series"), as_of_date
        )
        diagnostics = diagnose_walk_forward_ledger(
            ledger, visible_series=visible_series
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, DrawdownWalkForwardDiagnosticError):
            raise
        raise DrawdownWalkForwardDiagnosticError(str(exc)) from exc
    return diagnostics


def diagnose_walk_forward_ledger(
    ledger_body: dict[str, Any], *, visible_series: list[dict[str, Any]]
) -> dict[str, Any]:
    events = ledger_body.get("event_evaluations")
    if not isinstance(events, list):
        raise DrawdownWalkForwardDiagnosticError(
            "walk-forward evaluations must be a list"
        )
    date_indexes = _date_indexes(visible_series)
    expected = [
        (family, level, probability)
        for family, levels in THRESHOLD_FAMILIES
        for level, probability in levels
    ]
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {
        (family, level): [] for family, level, _ in expected
    }
    for sequence, event in enumerate(events, start=1):
        if event.get("event_sequence") != sequence:
            raise DrawdownWalkForwardDiagnosticError(
                "walk-forward events must be in sequence"
            )
        training = event["training_snapshot"]["threshold_statistics"]
        evaluations = event["threshold_evaluations"]
        pairs = [
            (row["threshold_family"], row["threshold_level"])
            for row in training
        ]
        evaluation_pairs = [
            (row["threshold_family"], row["threshold_level"])
            for row in evaluations
        ]
        expected_pairs = [(family, level) for family, level, _ in expected]
        if pairs != expected_pairs or evaluation_pairs != expected_pairs:
            raise DrawdownWalkForwardDiagnosticError(
                "threshold groups must use the approved order"
            )
        for snapshot, evaluation in zip(training, evaluations, strict=True):
            grouped[(snapshot["threshold_family"], snapshot["threshold_level"])].append(
                (event, {"training": snapshot, "evaluation": evaluation})
            )

    diagnostics = []
    for family, level, probability in expected:
        rows = grouped[(family, level)]
        diagnostics.append(
            {
                "threshold_family": family,
                "threshold_level": level,
                "threshold_probability_or_fraction": probability,
                "status_support": _status_support(rows),
                "training_support": _training_support(rows),
                "threshold_depth_stability": _depth_stability(rows),
                "training_metric_trajectories": _metric_trajectories(rows),
                "attainment_prequential_diagnostic": _attainment(rows),
                "trigger_recovery_prequential_diagnostics": _recovery(
                    rows, "trigger_price_recovery", date_indexes, len(visible_series)
                ),
                "peak_recovery_prequential_diagnostics": _recovery(
                    rows, "peak_recovery", date_indexes, len(visible_series)
                ),
                "forward_return_prequential_diagnostics": _forward_returns(rows),
            }
        )
    return {
        "period": ledger_body.get("period"),
        "summary": _summary(diagnostics),
        "threshold_diagnostics": diagnostics,
    }


def _status_support(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, int]:
    result = {
        "event_evaluation_count": len(rows),
        "completed_test_event_count": 0,
        "open_test_event_count": 0,
        "insufficient_history_count": 0,
        "threshold_available_count": 0,
        "reached_count": 0,
        "not_reached_completed_count": 0,
        "not_reached_open_censored_count": 0,
    }
    for event, pair in rows:
        completed = event["event_completed_in_source"]
        result["completed_test_event_count" if completed else "open_test_event_count"] += 1
        status = pair["evaluation"]["test_cohort"]["threshold_status"]
        if status == "insufficient_history":
            result["insufficient_history_count"] += 1
        elif status == "reached":
            result["threshold_available_count"] += 1
            result["reached_count"] += 1
        elif status == "not_reached":
            result["threshold_available_count"] += 1
            field = (
                "not_reached_completed_count"
                if completed
                else "not_reached_open_censored_count"
            )
            result[field] += 1
        else:
            raise DrawdownWalkForwardDiagnosticError("invalid threshold status")
    return result


def _training_support(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    paths: list[tuple[str, Callable[[dict[str, Any]], Any]]] = [
        ("coverage.threshold_available_event_count", lambda x: x["coverage"]["threshold_available_event_count"]),
        ("coverage.reached_event_count", lambda x: x["coverage"]["reached_event_count"]),
        ("trigger_price_recovery.sample_count", lambda x: x["trigger_price_recovery"]["sample_count"]),
        ("peak_recovery.sample_count", lambda x: x["peak_recovery"]["sample_count"]),
    ]
    for sessions, label in HORIZONS:
        paths.append(
            (
                f"horizon_outcomes.{label}.observed_window_count",
                lambda x, sessions=sessions: _horizon_row(x["horizon_outcomes"], sessions)["observed_window_count"],
            )
        )
    return {
        name: _integer_trajectory(rows, getter)
        for name, getter in paths
    }


def _integer_trajectory(rows: list[tuple[dict[str, Any], dict[str, Any]]], getter: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    points = []
    for event, pair in rows:
        value = getter(pair["training"])
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise DrawdownWalkForwardDiagnosticError("support trajectory must contain nonnegative integers")
        points.append((event["event_sequence"], value))
    return _basic_trajectory(points)


def _depth_stability(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    points = []
    for event, pair in rows:
        cohort = pair["evaluation"]["test_cohort"]
        if cohort["threshold_status"] != "insufficient_history":
            depth = cohort["threshold_depth"]
            if not _finite_number(depth) or depth <= 0:
                raise DrawdownWalkForwardDiagnosticError("threshold depth must be positive and finite")
            points.append((event["event_sequence"], float(depth)))
    basic = _basic_trajectory(points)
    values = [value for _, value in points]
    absolute = [abs(current - previous) for previous, current in zip(values, values[1:])]
    relative = [step / previous for previous, step in zip(values, absolute)]
    return {
        "available_count": basic["defined_count"],
        "first_event_sequence": basic["first_event_sequence"],
        "last_event_sequence": basic["last_event_sequence"],
        "first_depth": basic["first_value"],
        "last_depth": basic["last_value"],
        "minimum_depth": basic["minimum"],
        "maximum_depth": basic["maximum"],
        "p50_depth": basic["p50"],
        "range": _difference(basic["maximum"], basic["minimum"]),
        "adjacent_pair_count": len(absolute),
        "mean_absolute_step": _mean(absolute),
        "p50_absolute_step": _quantile(absolute),
        "maximum_absolute_step": max(absolute) if absolute else None,
        "mean_relative_step": _mean(relative),
        "maximum_relative_step": max(relative) if relative else None,
    }


def _metric_trajectories(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    paths: list[tuple[str, Callable[[dict[str, Any]], Any], bool]] = [
        ("coverage.attainment_rate", lambda x: x["coverage"]["attainment_rate"], True)
    ]
    for field in ("trigger_price_recovery", "peak_recovery"):
        for sessions, label in HORIZONS:
            paths.append((f"{field}.{label}.recovery_probability", lambda x, field=field, sessions=sessions: _horizon_row(x[field]["fixed_horizons"], sessions)["recovery_probability"], True))
    for sessions, label in HORIZONS:
        paths.append((f"horizon_outcomes.{label}.forward_return_distribution.p50", lambda x, sessions=sessions: _horizon_row(x["horizon_outcomes"], sessions)["forward_return_distribution"]["p50"], False))
    return [_metric_trajectory(name, rows, getter, probability) for name, getter, probability in paths]


def _metric_trajectory(name: str, rows: list[tuple[dict[str, Any], dict[str, Any]]], getter: Callable[[dict[str, Any]], Any], probability: bool) -> dict[str, Any]:
    points = []
    null_count = 0
    for event, pair in rows:
        value = getter(pair["training"])
        if value is None:
            null_count += 1
            continue
        if not _finite_number(value) or (probability and not 0 <= value <= 1):
            raise DrawdownWalkForwardDiagnosticError("training metric is invalid")
        points.append((event["event_sequence"], float(value)))
    basic = _basic_trajectory(points)
    values = [value for _, value in points]
    steps = [abs(current - previous) for previous, current in zip(values, values[1:])]
    zero_crossings = sum(previous * current < 0 for previous, current in zip(values, values[1:]))
    return {
        "metric": name,
        "defined_count": len(values),
        "null_count": null_count,
        "first_event_sequence": basic["first_event_sequence"],
        "last_event_sequence": basic["last_event_sequence"],
        "first_value": basic["first_value"],
        "last_value": basic["last_value"],
        "minimum": basic["minimum"],
        "maximum": basic["maximum"],
        "range": _difference(basic["maximum"], basic["minimum"]),
        "mean": _mean(values),
        "p50": _quantile(values),
        "adjacent_pair_count": len(steps),
        "mean_absolute_step": _mean(steps),
        "p50_absolute_step": _quantile(steps),
        "maximum_absolute_step": max(steps) if steps else None,
        "zero_crossing_count": zero_crossings,
    }


def _attainment(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    predictions: list[float] = []
    outcomes: list[int] = []
    unavailable = unresolved = positives = negatives = 0
    for event, pair in rows:
        status = pair["evaluation"]["test_cohort"]["threshold_status"]
        if status == "insufficient_history":
            continue
        if status == "not_reached" and not event["event_completed_in_source"]:
            unresolved += 1
            continue
        actual = 1 if status == "reached" else 0
        predicted = pair["training"]["coverage"]["attainment_rate"]
        if predicted is None:
            unavailable += 1
            continue
        _probability(predicted)
        predictions.append(float(predicted))
        outcomes.append(actual)
        positives += actual
        negatives += 1 - actual
    return _binary_diagnostic(predictions, outcomes, unavailable, unresolved, positives, negatives)


def _recovery(rows: list[tuple[dict[str, Any], dict[str, Any]]], field: str, date_indexes: dict[str, int], visible_count: int) -> list[dict[str, Any]]:
    result = []
    for sessions, label in HORIZONS:
        predictions: list[float] = []
        outcomes: list[int] = []
        reached = unavailable = unresolved = recovered = not_recovered = 0
        for _event, pair in rows:
            evaluation = pair["evaluation"]
            if evaluation["test_cohort"]["threshold_status"] != "reached":
                continue
            reached += 1
            outcome = evaluation["test_outcome"]
            recovery = outcome[field]
            if recovery["status"] == "observed":
                actual = int(recovery["sessions_from_trigger"] <= sessions)
            elif recovery["status"] == "censored":
                trigger_date = outcome["trigger_date"]
                if trigger_date not in date_indexes:
                    raise DrawdownWalkForwardDiagnosticError("trigger date is outside visible series")
                censor_sessions = visible_count - 1 - date_indexes[trigger_date]
                if censor_sessions < sessions:
                    unresolved += 1
                    continue
                actual = 0
            else:
                raise DrawdownWalkForwardDiagnosticError("invalid recovery status")
            predicted = _horizon_row(pair["training"][field]["fixed_horizons"], sessions)["recovery_probability"]
            if predicted is None:
                unavailable += 1
                continue
            _probability(predicted)
            predictions.append(float(predicted))
            outcomes.append(actual)
            recovered += actual
            not_recovered += 1 - actual
        binary = _binary_values(predictions, outcomes)
        result.append({
            "horizon_sessions": sessions,
            "label": label,
            "reached_test_count": reached,
            "predicted_unavailable_count": unavailable,
            "resolved_count": len(outcomes),
            "unresolved_censored_count": unresolved,
            "recovered_through_horizon_count": recovered,
            "not_recovered_through_horizon_count": not_recovered,
            **binary,
        })
    return result


def _forward_returns(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    result = []
    for sessions, label in HORIZONS:
        errors: list[float] = []
        sign_count = iqr_count = reached = observed = censored = unavailable = 0
        for _event, pair in rows:
            evaluation = pair["evaluation"]
            if evaluation["test_cohort"]["threshold_status"] != "reached":
                continue
            reached += 1
            test = _horizon_row(evaluation["test_outcome"]["horizons"], sessions)
            if test["status"] == "censored":
                censored += 1
                continue
            if test["status"] != "observed":
                raise DrawdownWalkForwardDiagnosticError("invalid forward window status")
            observed += 1
            training = _horizon_row(pair["training"]["horizon_outcomes"], sessions)["forward_return_distribution"]
            p25, p50, p75 = (training[key] for key in ("p25", "p50", "p75"))
            if any(value is None for value in (p25, p50, p75)):
                unavailable += 1
                continue
            if not all(_finite_number(value) for value in (p25, p50, p75)) or not p25 <= p50 <= p75:
                raise DrawdownWalkForwardDiagnosticError("invalid training return distribution")
            actual = test["forward_return"]
            if not _finite_number(actual):
                raise DrawdownWalkForwardDiagnosticError("invalid test forward return")
            errors.append(float(actual - p50))
            sign_count += int((actual > 0 and p50 > 0) or (actual < 0 and p50 < 0) or (actual == 0 and p50 == 0))
            iqr_count += int(p25 <= actual <= p75)
        absolute = [abs(value) for value in errors]
        count = len(errors)
        result.append({
            "horizon_sessions": sessions,
            "label": label,
            "reached_test_count": reached,
            "test_window_observed_count": observed,
            "test_window_censored_count": censored,
            "training_distribution_unavailable_count": unavailable,
            "comparable_count": count,
            "mean_signed_error_vs_training_p50": _mean(errors),
            "mean_absolute_error_vs_training_p50": _mean(absolute),
            "p50_absolute_error_vs_training_p50": _quantile(absolute),
            "sign_agreement_count": sign_count,
            "sign_agreement_rate": _ratio(sign_count, count),
            "inside_training_iqr_count": iqr_count,
            "inside_training_iqr_rate": _ratio(iqr_count, count),
        })
    return result


def _binary_diagnostic(predictions: list[float], outcomes: list[int], unavailable: int, unresolved: int, positives: int, negatives: int) -> dict[str, Any]:
    return {
        "eligible_count": len(outcomes),
        "predicted_unavailable_count": unavailable,
        "unresolved_open_count": unresolved,
        "positive_count": positives,
        "negative_count": negatives,
        **_binary_values(predictions, outcomes),
        "mean_absolute_calibration_gap": _absolute_calibration_gap(predictions, outcomes),
    }


def _binary_values(predictions: list[float], outcomes: list[int]) -> dict[str, Any]:
    mean_predicted = _mean(predictions)
    observed = _mean(outcomes)
    gap = observed - mean_predicted if observed is not None and mean_predicted is not None else None
    return {
        "mean_predicted_probability": mean_predicted,
        "observed_frequency": observed,
        "calibration_gap": gap,
        "brier_score": _mean([(predicted - actual) ** 2 for predicted, actual in zip(predictions, outcomes, strict=True)]),
    }


def _absolute_calibration_gap(predictions: list[float], outcomes: list[int]) -> float | None:
    values = _binary_values(predictions, outcomes)
    gap = values["calibration_gap"]
    return abs(gap) if gap is not None else None


def _basic_trajectory(points: list[tuple[int, float]]) -> dict[str, Any]:
    values = [value for _, value in points]
    return {
        "defined_count": len(values),
        "first_event_sequence": points[0][0] if points else None,
        "last_event_sequence": points[-1][0] if points else None,
        "first_value": values[0] if values else None,
        "last_value": values[-1] if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "p50": _quantile(values),
    }


def _summary(diagnostics: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "threshold_group_count": len(diagnostics),
        "event_evaluation_count": sum(row["status_support"]["event_evaluation_count"] for row in diagnostics) // len(diagnostics) if diagnostics else 0,
        "total_reached_evaluations": sum(row["status_support"]["reached_count"] for row in diagnostics),
    }


def _visible_series(raw: Any, as_of_date: str | None) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise DrawdownWalkForwardDiagnosticError("drawdown_series must be non-empty")
    rows = raw
    if as_of_date is not None:
        matches = [index for index, row in enumerate(raw) if isinstance(row, dict) and row.get("date") == as_of_date]
        if len(matches) != 1:
            raise DrawdownWalkForwardDiagnosticError("as_of_date must be an actual input trading date")
        rows = raw[: matches[0] + 1]
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str) or not _finite_number(row.get("close")):
            raise DrawdownWalkForwardDiagnosticError("visible drawdown row is invalid")
        result.append({"date": row["date"], "close": float(row["close"])})
    return result


def _date_indexes(series: list[dict[str, Any]]) -> dict[str, int]:
    indexes = {row["date"]: index for index, row in enumerate(series)}
    if len(indexes) != len(series):
        raise DrawdownWalkForwardDiagnosticError("visible series dates must be unique")
    return indexes


def _horizon_row(rows: list[dict[str, Any]], sessions: int) -> dict[str, Any]:
    matches = [row for row in rows if row.get("horizon_sessions") == sessions]
    if len(matches) != 1:
        raise DrawdownWalkForwardDiagnosticError("horizon must identify exactly one row")
    return matches[0]


def _quantile(values: list[float]) -> float | None:
    return linear_quantile(values, 0.5) if values else None


def _mean(values: list[float] | list[int]) -> float | None:
    return sum(values) / len(values) if values else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _difference(high: float | None, low: float | None) -> float | None:
    return high - low if high is not None and low is not None else None


def _probability(value: Any) -> None:
    if not _finite_number(value) or not 0 <= value <= 1:
        raise DrawdownWalkForwardDiagnosticError("probability must be in [0, 1]")


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
