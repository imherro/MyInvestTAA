from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

from decision.v11_current.validation import canonical_state_hash
from engine.asset_registry.loader import ROOT


V11_CURRENT_ALLOCATION_REPORT = ROOT / "reports" / "v11_current_allocation.json"


def write_v11_current_allocation(
    value: dict,
    path: Path | None = None,
) -> Path:
    target = path or V11_CURRENT_ALLOCATION_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return target


def load_v11_current_allocation(
    path: Path | None = None,
    *,
    verify_sources: bool | None = None,
) -> dict:
    target = path or V11_CURRENT_ALLOCATION_REPORT
    if not target.exists():
        return {
            "available": False,
            "status": "unavailable",
            "message": "V11 current allocation snapshot not generated yet",
        }
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "status": "unavailable",
            "message": f"V11 current allocation snapshot is invalid: {type(exc).__name__}",
        }
    schema_errors = _schema_errors(value)
    if schema_errors:
        return {
            "available": False,
            "status": "unavailable",
            "message": "V11 current allocation snapshot schema is incomplete",
            "errors": schema_errors,
        }
    should_verify = (
        target.resolve() == V11_CURRENT_ALLOCATION_REPORT.resolve()
        if verify_sources is None
        else verify_sources
    )
    if should_verify:
        verification = verify_v11_current_allocation_sources(value)
        value["source_integrity"] = verification
        if not verification["verified"]:
            value["available"] = False
            value["status"] = "unavailable"
            value["production_actionable"] = False
            value["trading_instruction"] = False
            value["message"] = (
                "V11 current allocation source drifted; rebuild required"
            )
            value["errors"] = list(
                dict.fromkeys(value.get("errors", []) + verification["errors"])
            )
    return value


def verify_v11_current_allocation_sources(value: dict) -> dict:
    integrity = value.get("source_integrity", {})
    errors: list[str] = []
    diagnosis_path = _safe_project_path(
        integrity.get("diagnosis_report_path"), "diagnosis report", errors
    )
    engine_path = _safe_project_path(
        integrity.get("taa_engine_path"), "TAA engine", errors
    )
    diagnosis_code_path = _safe_project_path(
        integrity.get("strategy_diagnosis_code_path"),
        "strategy diagnosis code",
        errors,
    )
    _verify_file_hash(
        diagnosis_path,
        integrity.get("diagnosis_report_hash"),
        "diagnosis report",
        errors,
    )
    _verify_file_hash(
        engine_path, integrity.get("taa_engine_hash"), "TAA engine", errors
    )
    _verify_file_hash(
        diagnosis_code_path,
        integrity.get("strategy_diagnosis_code_hash"),
        "strategy diagnosis code",
        errors,
    )

    source = {}
    if diagnosis_path and diagnosis_path.exists():
        try:
            diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
            source = diagnosis.get("diagnosis", {}).get(
                "v11_current_state_source", {}
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append("diagnosis report cannot be read for V11 state verification")
    try:
        actual_state_hash = canonical_state_hash(source) if source else None
    except (TypeError, ValueError):
        actual_state_hash = None
    expected_state_hash = integrity.get("source_state_hash")
    if not expected_state_hash or actual_state_hash != expected_state_hash:
        errors.append("V11 source state hash mismatch")
    if source.get("source_state_hash") != expected_state_hash:
        errors.append("diagnosis V11 source state identity mismatch")
    if source.get("state_date") != value.get("source_state_date"):
        errors.append("V11 snapshot state date drifted")
    if source.get("weights_percent") != value.get("allocation_percent"):
        errors.append("V11 snapshot allocation drifted from diagnosis state")

    return {
        **integrity,
        "verified": not errors,
        "errors": list(dict.fromkeys(errors)),
    }


def _schema_errors(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["snapshot root must be an object"]
    required = (
        "available",
        "strategy",
        "status",
        "production_candidate",
        "production_actionable",
        "trading_instruction",
        "as_of",
        "source_state_date",
        "generated_at",
        "allocation",
        "allocation_percent",
        "equity_weight",
        "cash_weight",
        "selected_assets",
        "regime",
        "risk_budget",
        "exposure_decision",
        "target_weights_percent",
        "assumptions",
        "source_integrity",
        "constraint_checks",
        "warnings",
    )
    errors = [f"missing field: {field}" for field in required if field not in value]
    for field in ("available", "production_candidate", "production_actionable", "trading_instruction"):
        if field in value and not isinstance(value[field], bool):
            errors.append(f"{field} must be boolean")
    return errors


def _safe_project_path(value: object, label: str, errors: list[str]) -> Path | None:
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


def _verify_file_hash(
    path: Path | None,
    expected: object,
    label: str,
    errors: list[str],
) -> None:
    if path is None:
        return
    if not path.exists():
        errors.append(f"{label} is missing")
        return
    if not isinstance(expected, str) or _sha256_file(path) != expected:
        errors.append(f"{label} hash mismatch")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
