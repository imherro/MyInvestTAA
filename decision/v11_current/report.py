from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from decision.v11_current.validation import (
    load_snapshot_diagnosis_report,
    validate_v11_current_allocation_snapshot,
)
from engine.asset_registry.loader import ROOT


V11_CURRENT_ALLOCATION_REPORT = ROOT / "reports" / "v11_current_allocation.json"


def write_v11_current_allocation(
    value: dict,
    path: Path | None = None,
) -> Path:
    target = path or V11_CURRENT_ALLOCATION_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(
                value,
                handle,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
        _fsync_directory(target.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def load_v11_current_allocation(
    path: Path | None = None,
    *,
    verify_sources: bool | None = None,
) -> dict:
    target = path or V11_CURRENT_ALLOCATION_REPORT
    if not target.exists():
        return _unavailable("V11 current allocation snapshot not generated yet")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _unavailable(
            f"V11 current allocation snapshot is invalid: {type(exc).__name__}"
        )
    schema_errors = _schema_errors(value)
    if schema_errors:
        return _unavailable(
            "V11 current allocation snapshot schema is incomplete", schema_errors
        )

    should_verify_files = (
        target.resolve() == V11_CURRENT_ALLOCATION_REPORT.resolve()
        if verify_sources is None
        else verify_sources
    )
    diagnosis, diagnosis_errors = load_snapshot_diagnosis_report(value)
    if diagnosis_errors or diagnosis is None:
        verification = {
            "valid": False,
            "errors": diagnosis_errors,
            "source_integrity": {
                **value.get("source_integrity", {}),
                "verified": False,
                "semantic_verified": False,
                "errors": diagnosis_errors,
            },
        }
    else:
        verification = validate_v11_current_allocation_snapshot(
            value,
            diagnosis,
            verify_source_files=should_verify_files,
        )
    value["source_integrity"] = verification["source_integrity"]
    if not verification["valid"]:
        value["available"] = False
        value["status"] = "unavailable"
        value["production_actionable"] = False
        value["trading_instruction"] = False
        value["message"] = (
            "V11 current allocation snapshot semantic integrity failed"
        )
        value["errors"] = list(
            dict.fromkeys(value.get("errors", []) + verification["errors"])
        )
    return value


def verify_v11_current_allocation_sources(value: dict) -> dict:
    diagnosis, diagnosis_errors = load_snapshot_diagnosis_report(value)
    if diagnosis_errors or diagnosis is None:
        return {
            **value.get("source_integrity", {}),
            "verified": False,
            "semantic_verified": False,
            "errors": diagnosis_errors,
        }
    return validate_v11_current_allocation_snapshot(
        value, diagnosis, verify_source_files=True
    )["source_integrity"]


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
        "report_path",
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
    for field in (
        "available",
        "production_candidate",
        "production_actionable",
        "trading_instruction",
    ):
        if field in value and not isinstance(value[field], bool):
            errors.append(f"{field} must be boolean")
    return errors


def _unavailable(message: str, errors: list[str] | None = None) -> dict:
    return {
        "available": False,
        "status": "unavailable",
        "production_actionable": False,
        "trading_instruction": False,
        "message": message,
        **({"errors": errors} if errors else {}),
    }


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
