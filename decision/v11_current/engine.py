from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

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

    diagnosis_hash = _sha256_file(diagnosis_path) if diagnosis_path.exists() else None
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

    weights_percent = source.get("weights_percent", {})
    allocation = {
        asset_id: round(float(weight) / 100.0, 12)
        for asset_id, weight in weights_percent.items()
        if isinstance(weight, (int, float)) and not isinstance(weight, bool)
    }
    allocation_sum = round(sum(allocation.values()), 12) if allocation else None
    if allocation_sum is not None and abs(allocation_sum - 1.0) > 0.00000001:
        errors.append("V11 allocation fractions must sum to 1")
    cash_weight = allocation.get("CASH")
    equity_weight = round(1.0 - cash_weight, 12) if cash_weight is not None else None
    source_integrity = {
        "diagnosis_report_path": _relative(diagnosis_path),
        "diagnosis_report_hash": diagnosis_hash,
        "source_state_hash": source.get("source_state_hash"),
        "taa_engine_path": _relative(TAA_ENGINE),
        "taa_engine_hash": _sha256_file(TAA_ENGINE) if TAA_ENGINE.exists() else None,
        "strategy_diagnosis_code_path": _relative(STRATEGY_DIAGNOSIS_CODE),
        "strategy_diagnosis_code_hash": _sha256_file(STRATEGY_DIAGNOSIS_CODE)
        if STRATEGY_DIAGNOSIS_CODE.exists()
        else None,
        "verified": not errors,
        "errors": list(dict.fromkeys(errors)),
    }
    violations = list(dict.fromkeys(errors))
    return {
        "available": not violations,
        "strategy": CANONICAL_STRATEGY,
        "status": "production_candidate_snapshot" if not violations else "unavailable",
        "production_candidate": True,
        "production_actionable": False,
        "trading_instruction": False,
        "as_of": market_data_as_of,
        "source_state_date": source.get("state_date"),
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "report_path": "reports/v11_current_allocation.json",
        "allocation": allocation if not violations else {},
        "allocation_percent": weights_percent if not violations else {},
        "equity_weight": equity_weight if not violations else None,
        "cash_weight": cash_weight if not violations else None,
        "selected_assets": source.get("selected_assets", []) if not violations else [],
        "regime": source.get("regime", {}) if not violations else {},
        "risk_budget": source.get("risk_budget", {}) if not violations else {},
        "exposure_decision": source.get("exposure_decision", {}) if not violations else {},
        "target_weights_percent": source.get("target_weights_percent", {})
        if not violations
        else {},
        "assumptions": source.get("assumptions", {}) if not violations else {},
        "source_integrity": source_integrity,
        "constraint_checks": {
            "weight_sum_percent": validation.weight_sum_percent,
            "weight_sum_fraction": allocation_sum,
            "negative_weights": validation.negative_weights,
            "selected_asset_mismatches": validation.selected_asset_mismatches,
            "violations": violations,
        },
        "errors": violations,
        "warnings": [
            "This is an offline V11 model allocation snapshot, not an order or trading instruction."
        ],
    }


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
