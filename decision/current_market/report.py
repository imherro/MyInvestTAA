from __future__ import annotations

import json
import hashlib
from pathlib import Path

from engine.asset_registry.loader import ROOT


CURRENT_MARKET_DECISION_REPORT = ROOT / "reports" / "current_market_decision.json"


def write_current_market_decision(value: dict, path: Path | None = None) -> Path:
    target = path or CURRENT_MARKET_DECISION_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def load_current_market_decision(
    path: Path | None = None, *, verify_sources: bool | None = None
) -> dict:
    target = path or CURRENT_MARKET_DECISION_REPORT
    if not target.exists():
        return {
            "available": False,
            "message": "current market decision report not generated yet",
        }
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "status": "unavailable",
            "message": f"current market decision report is invalid: {type(exc).__name__}",
        }
    schema_errors = _schema_errors(value)
    if schema_errors:
        return {
            "available": False,
            "status": "unavailable",
            "message": "current market decision report schema is incomplete",
            "errors": schema_errors,
        }
    should_verify = (
        target.resolve() == CURRENT_MARKET_DECISION_REPORT.resolve()
        if verify_sources is None
        else verify_sources
    )
    if should_verify:
        verification = _verify_source_manifest(value["source_manifest"])
        value["source_hash_verification"] = verification
        if not verification["valid"]:
            value["available"] = False
            value["status"] = "unavailable"
            value["ready_for_user_review"] = False
            value["production_actionable"] = False
            value["message"] = (
                "current market decision snapshot source drifted; rebuild required"
            )
    return value


def _schema_errors(value) -> list[str]:
    if not isinstance(value, dict):
        return ["report root must be an object"]
    required = (
        "available",
        "status",
        "ready_for_user_review",
        "production_actionable",
        "decision_date",
        "generated_at",
        "market_data_as_of",
        "governance_state_as_of",
        "snapshot_mode",
        "market_state",
        "production_candidate",
        "research_allocation",
        "execution_shadow",
        "execution_validation",
        "source_manifest",
    )
    errors = [f"missing field: {field}" for field in required if field not in value]
    if "available" in value and not isinstance(value["available"], bool):
        errors.append("available must be boolean")
    if "source_manifest" in value and not isinstance(value["source_manifest"], dict):
        errors.append("source_manifest must be an object")
    return errors


def _verify_source_manifest(manifest: dict) -> dict:
    errors = []
    required_count = 0
    verified_count = 0
    for name, row in manifest.items():
        if not isinstance(row, dict) or not row.get("required"):
            continue
        required_count += 1
        path_value = row.get("path")
        expected = row.get("sha256")
        if not path_value or not expected:
            errors.append(f"required source metadata incomplete: {name}")
            continue
        source = (ROOT / path_value).resolve()
        try:
            source.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f"required source path escapes project root: {name}")
            continue
        if not source.exists():
            errors.append(f"required source missing: {name}")
            continue
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"required source hash mismatch: {name}")
            continue
        verified_count += 1
    if required_count == 0:
        errors.append("required source manifest is empty")
    return {
        "valid": not errors,
        "required_count": required_count,
        "verified_count": verified_count,
        "errors": errors,
    }
