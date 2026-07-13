from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from decision.v11_current.derive import (
    NON_TRADING_WARNING,
    derive_v11_snapshot_fields,
    snapshot_payload_hash,
)
from decision.v11_current.validation import (
    CANONICAL_STRATEGY,
    validate_v11_state_source,
)
from engine.asset_registry.loader import ROOT


DIAGNOSIS_REPORT = ROOT / "reports" / "strategy_diagnosis_report.json"
TAA_ENGINE = ROOT / "backtest" / "taa" / "engine.py"
STRATEGY_DIAGNOSIS_CODE = ROOT / "data_pipeline" / "strategy_diagnosis.py"


def build_v11_current_allocation_snapshot(
    diagnosis_report: dict,
    *,
    market_data_as_of: str,
    generated_at: str | None = None,
    diagnosis_report_path: Path | None = None,
) -> dict:
    diagnosis_path = diagnosis_report_path or DIAGNOSIS_REPORT
    source = diagnosis_report.get("diagnosis", {}).get(
        "v11_current_state_source", {}
    )
    validation = validate_v11_state_source(source, market_data_as_of)
    errors = list(validation.errors)
    dataset_end = diagnosis_report.get("dataset", {}).get("period", {}).get("end")
    if dataset_end != market_data_as_of:
        errors.append("diagnosis dataset end must equal market_data_as_of")

    diagnosis_hash = _required_file_hash(
        diagnosis_path, "strategy diagnosis report", errors
    )
    if not diagnosis_path.exists():
        errors.append("strategy diagnosis report file is unavailable")
    else:
        try:
            file_payload = json.loads(diagnosis_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            file_payload = None
            errors.append("strategy diagnosis report file is invalid")
        if file_payload != diagnosis_report:
            errors.append("diagnosis report payload does not match source file")

    taa_engine_hash = _required_file_hash(TAA_ENGINE, "TAA engine", errors)
    strategy_diagnosis_code_hash = _required_file_hash(
        STRATEGY_DIAGNOSIS_CODE, "strategy diagnosis code", errors
    )
    try:
        derived = derive_v11_snapshot_fields(source)
    except (TypeError, ValueError, OverflowError):
        derived = {}
        errors.append("V11 snapshot fields cannot be derived from diagnosis state")
    errors = list(dict.fromkeys(errors))
    valid = not errors
    empty_fields = {
        "allocation_percent": {},
        "allocation": {},
        "equity_weight": None,
        "cash_weight": None,
        "selected_assets": [],
        "regime": {},
        "risk_budget": {},
        "exposure_decision": {},
        "target_weights_percent": {},
        "assumptions": {},
        "constraint_checks": {
            "weight_sum_percent": validation.weight_sum_percent,
            "weight_sum_fraction": validation.weight_sum_fraction,
            "negative_weights": validation.negative_weights,
            "selected_asset_mismatches": validation.selected_asset_mismatches,
            "violations": errors,
        },
    }
    payload_fields = derived if valid else empty_fields
    source_integrity = {
        "diagnosis_report_path": _relative(diagnosis_path),
        "diagnosis_report_hash": diagnosis_hash,
        "source_state_hash": source.get("source_state_hash"),
        "taa_engine_path": _relative(TAA_ENGINE),
        "taa_engine_hash": taa_engine_hash,
        "strategy_diagnosis_code_path": _relative(STRATEGY_DIAGNOSIS_CODE),
        "strategy_diagnosis_code_hash": strategy_diagnosis_code_hash,
        "snapshot_payload_hash": None,
        "verified": valid,
        "semantic_verified": valid,
        "errors": errors,
    }
    snapshot = {
        "available": valid,
        "strategy": CANONICAL_STRATEGY,
        "status": "production_candidate_snapshot" if valid else "unavailable",
        "production_candidate": True,
        "production_actionable": False,
        "trading_instruction": False,
        "as_of": market_data_as_of,
        "source_state_date": source.get("state_date"),
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "report_path": "reports/v11_current_allocation.json",
        **payload_fields,
        "source_integrity": source_integrity,
        "errors": errors,
        "warnings": [NON_TRADING_WARNING],
    }
    snapshot["source_integrity"]["snapshot_payload_hash"] = (
        snapshot_payload_hash(snapshot)
    )
    return snapshot


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required_file_hash(path: Path, label: str, errors: list[str]) -> str | None:
    if not path.exists():
        errors.append(f"{label} is missing")
        return None
    try:
        return _sha256_file(path)
    except OSError:
        errors.append(f"{label} hash cannot be computed")
        return None
