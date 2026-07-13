from __future__ import annotations

from datetime import date
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from decision.v11_current.models import V11ValidationResult
from engine.asset_registry.loader import ROOT


CANONICAL_STRATEGY = "V11_PRODUCTION_FUSION"
CANONICAL_REPORT_PATH = "reports/v11_current_allocation.json"


def canonical_json_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_state_payload(source: dict) -> dict:
    return {
        key: source.get(key)
        for key in (
            "strategy",
            "state_date",
            "period",
            "weights_percent",
            "selected_assets",
            "regime",
            "risk_budget",
            "exposure_decision",
            "target_weights_percent",
            "assumptions",
        )
    }


def canonical_state_hash(source: dict) -> str:
    return canonical_json_hash(canonical_state_payload(source))


def parse_iso_date(value: object, label: str, errors: list[str]) -> date | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} is required")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be a valid ISO date")
        return None


def validate_v11_state_source(source: object, market_data_as_of: str) -> V11ValidationResult:
    errors: list[str] = []
    negative_weights: list[str] = []
    selected_mismatches: list[str] = []
    if not isinstance(source, dict):
        return V11ValidationResult(
            False,
            ["diagnosis V11 current state source must be an object"],
            None,
            None,
            [],
            [],
        )
    if source.get("available") is not True:
        errors.append("diagnosis V11 current state source is unavailable")
    if source.get("strategy") != CANONICAL_STRATEGY:
        errors.append("V11 strategy identity mismatch")

    cutoff = parse_iso_date(market_data_as_of, "market_data_as_of", errors)
    state_date = parse_iso_date(source.get("state_date"), "V11 state_date", errors)
    period = source.get("period")
    if not isinstance(period, dict):
        errors.append("V11 result period must be an object")
        period = {}
    period_start = parse_iso_date(period.get("start"), "V11 result period start", errors)
    period_end = parse_iso_date(period.get("end"), "V11 result period end", errors)
    if period_start and period_end and period_start > period_end:
        errors.append("V11 result period start must not be after end")
    if state_date and period_end and state_date != period_end:
        errors.append("V11 state_date must equal result period end")
    if state_date and cutoff and state_date > cutoff:
        errors.append("V11 state_date is after market data cutoff")

    weights = source.get("weights_percent")
    weight_sum_percent: float | None = None
    weight_sum_fraction: float | None = None
    positive_assets: set[str] = set()
    if not isinstance(weights, dict) or not weights:
        errors.append("V11 weights_percent must be a non-empty object")
    else:
        for asset_id, weight in weights.items():
            if not isinstance(asset_id, str) or not asset_id:
                errors.append("V11 weight asset id must be a non-empty string")
                continue
            if not _finite_number(weight):
                errors.append(f"V11 weight must be finite: {asset_id}")
                continue
            value = float(weight)
            if value < 0:
                negative_weights.append(asset_id)
            if asset_id != "CASH" and value > 0:
                positive_assets.add(asset_id)
        if "CASH" not in weights:
            errors.append("V11 weights_percent must include CASH")
        finite_values = [float(value) for value in weights.values() if _finite_number(value)]
        if len(finite_values) == len(weights):
            weight_sum_percent = round(sum(finite_values), 10)
            weight_sum_fraction = round(weight_sum_percent / 100.0, 12)
            if abs(weight_sum_percent - 100.0) > 0.000001:
                errors.append("V11 weights_percent must sum to 100")
        if negative_weights:
            errors.append("V11 weights_percent contains negative weights")

    selected = source.get("selected_assets")
    if not isinstance(selected, list) or any(
        not isinstance(asset_id, str) or not asset_id for asset_id in selected
    ):
        errors.append("V11 selected_assets must be list[str]")
    else:
        selected_set = set(selected)
        if len(selected_set) != len(selected):
            errors.append("V11 selected_assets must not contain duplicates")
        selected_mismatches = sorted(positive_assets.symmetric_difference(selected_set))
        if selected_mismatches:
            errors.append("V11 selected_assets do not match positive non-cash weights")

    assumptions = source.get("assumptions")
    if not isinstance(assumptions, dict):
        errors.append("V11 assumptions must be an object")
        assumptions = {}
    if assumptions.get("score_version") != "v11":
        errors.append("V11 score_version must be v11")
    if not _finite_number(assumptions.get("max_weight_step")) or float(
        assumptions.get("max_weight_step", 0)
    ) != 10.0:
        errors.append("V11 max_weight_step must equal 10.0")
    if assumptions.get("volatility_adjustment") is not True:
        errors.append("V11 volatility_adjustment must be true")
    from data_pipeline.strategy_diagnosis import V11_ROBUST_EXPOSURE_CONFIG

    if assumptions.get("robust_exposure_config") != V11_ROBUST_EXPOSURE_CONFIG:
        errors.append("V11 robust_exposure_config mismatch")

    expected_state_hash = source.get("source_state_hash")
    try:
        actual_state_hash = canonical_state_hash(source)
    except (TypeError, ValueError):
        actual_state_hash = None
        errors.append("V11 source state cannot be normalized")
    if not isinstance(expected_state_hash, str) or expected_state_hash != actual_state_hash:
        errors.append("V11 source state hash mismatch")

    return V11ValidationResult(
        not errors,
        list(dict.fromkeys(errors)),
        weight_sum_percent,
        weight_sum_fraction,
        negative_weights,
        selected_mismatches,
    )


def validate_v11_current_allocation_snapshot(
    snapshot: object,
    diagnosis_report: object,
    *,
    verify_source_files: bool = True,
) -> dict:
    errors: list[str] = []
    if not isinstance(snapshot, dict):
        return _snapshot_validation_result(
            {}, ["V11 current allocation snapshot must be an object"]
        )
    if not isinstance(diagnosis_report, dict):
        return _snapshot_validation_result(
            snapshot, ["strategy diagnosis report must be an object"]
        )

    source = diagnosis_report.get("diagnosis", {}).get(
        "v11_current_state_source", {}
    )
    as_of = snapshot.get("as_of")
    source_state_date = snapshot.get("source_state_date")
    parsed_as_of = parse_iso_date(as_of, "V11 snapshot as_of", errors)
    parsed_state_date = parse_iso_date(
        source_state_date, "V11 snapshot source_state_date", errors
    )
    if parsed_as_of and parsed_state_date and parsed_as_of != parsed_state_date:
        errors.append("V11 snapshot as_of must equal source_state_date")
    if source.get("state_date") != source_state_date:
        errors.append("V11 snapshot state date drifted")
    dataset_end = diagnosis_report.get("dataset", {}).get("period", {}).get("end")
    if dataset_end != as_of:
        errors.append("diagnosis dataset end must equal V11 snapshot as_of")

    source_validation = validate_v11_state_source(source, str(as_of or ""))
    errors.extend(source_validation.errors)

    if snapshot.get("strategy") != CANONICAL_STRATEGY:
        errors.append("V11 snapshot strategy identity mismatch")
    if snapshot.get("available") is not True:
        errors.append("V11 snapshot available must be true")
    if snapshot.get("status") != "production_candidate_snapshot":
        errors.append("V11 snapshot status mismatch")
    if snapshot.get("production_candidate") is not True:
        errors.append("V11 snapshot production_candidate must be true")
    if snapshot.get("production_actionable") is not False:
        errors.append("V11 snapshot production_actionable must be false")
    if snapshot.get("trading_instruction") is not False:
        errors.append("V11 snapshot trading_instruction must be false")
    if snapshot.get("report_path") != CANONICAL_REPORT_PATH:
        errors.append("V11 snapshot report_path mismatch")

    warnings = snapshot.get("warnings")
    from decision.v11_current.derive import (
        NON_TRADING_WARNING,
        derive_v11_snapshot_fields,
        snapshot_payload_hash,
    )

    if not isinstance(warnings, list) or NON_TRADING_WARNING not in warnings:
        errors.append("V11 snapshot non-trading warning is missing")

    try:
        derived = derive_v11_snapshot_fields(source)
    except (TypeError, ValueError, OverflowError):
        derived = {}
        errors.append("V11 snapshot fields cannot be derived from diagnosis state")
    for field in (
        "allocation_percent",
        "allocation",
        "equity_weight",
        "cash_weight",
        "selected_assets",
        "regime",
        "risk_budget",
        "exposure_decision",
        "target_weights_percent",
        "assumptions",
        "constraint_checks",
    ):
        if snapshot.get(field) != derived.get(field):
            errors.append(f"V11 snapshot semantic field mismatch: {field}")

    integrity = snapshot.get("source_integrity")
    if not isinstance(integrity, dict):
        integrity = {}
        errors.append("V11 snapshot source_integrity must be an object")
    expected_payload_hash = integrity.get("snapshot_payload_hash")
    try:
        actual_payload_hash = snapshot_payload_hash(snapshot)
    except (TypeError, ValueError):
        actual_payload_hash = None
        errors.append("V11 snapshot payload cannot be normalized")
    if (
        not isinstance(expected_payload_hash, str)
        or expected_payload_hash != actual_payload_hash
    ):
        errors.append("V11 snapshot payload hash mismatch")

    expected_state_hash = integrity.get("source_state_hash")
    try:
        actual_state_hash = canonical_state_hash(source)
    except (TypeError, ValueError):
        actual_state_hash = None
    if not expected_state_hash or expected_state_hash != actual_state_hash:
        errors.append("V11 source state hash mismatch")
    if source.get("source_state_hash") != expected_state_hash:
        errors.append("diagnosis V11 source state identity mismatch")

    if verify_source_files:
        _verify_snapshot_source_files(integrity, errors)

    return _snapshot_validation_result(
        snapshot,
        list(dict.fromkeys(errors)),
        actual_payload_hash=actual_payload_hash,
        integrity=integrity,
        derived=derived,
    )


def load_snapshot_diagnosis_report(snapshot: object) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    if not isinstance(snapshot, dict):
        return None, ["V11 current allocation snapshot must be an object"]
    integrity = snapshot.get("source_integrity", {})
    if not isinstance(integrity, dict):
        return None, ["V11 snapshot source_integrity must be an object"]
    path = _safe_project_path(
        integrity.get("diagnosis_report_path"), "diagnosis report", errors
    )
    if path is None or not path.exists():
        if path is not None:
            errors.append("diagnosis report is missing")
        return None, errors
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append("diagnosis report cannot be read for V11 state verification")
        return None, errors
    if not isinstance(value, dict):
        errors.append("diagnosis report root must be an object")
        return None, errors
    return value, errors


def _snapshot_validation_result(
    snapshot: dict,
    errors: list[str],
    *,
    actual_payload_hash: str | None = None,
    integrity: dict | None = None,
    derived: dict | None = None,
) -> dict:
    value = deepcopy(integrity or snapshot.get("source_integrity", {}))
    if not isinstance(value, dict):
        value = {}
    value["verified"] = not errors
    value["semantic_verified"] = not errors
    value["actual_snapshot_payload_hash"] = actual_payload_hash
    value["errors"] = errors
    return {
        "valid": not errors,
        "errors": errors,
        "source_integrity": value,
        "derived": derived or {},
    }


def _verify_snapshot_source_files(integrity: dict, errors: list[str]) -> None:
    for path_field, hash_field, label in (
        ("diagnosis_report_path", "diagnosis_report_hash", "diagnosis report"),
        ("taa_engine_path", "taa_engine_hash", "TAA engine"),
        (
            "strategy_diagnosis_code_path",
            "strategy_diagnosis_code_hash",
            "strategy diagnosis code",
        ),
    ):
        path = _safe_project_path(integrity.get(path_field), label, errors)
        if path is None:
            continue
        if not path.exists():
            errors.append(f"{label} is missing")
            continue
        expected = integrity.get(hash_field)
        if not isinstance(expected, str) or _sha256_file(path) != expected:
            errors.append(f"{label} hash mismatch")


def _safe_project_path(
    value: object, label: str, errors: list[str]
) -> Path | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} path is missing")
        return None
    path = (ROOT / value).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        errors.append(f"{label} path escapes project root")
        return None
    return path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
