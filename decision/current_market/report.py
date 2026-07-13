from __future__ import annotations

import json
from pathlib import Path

from decision.current_market.explain import decision_headline
from decision.current_market.source_policy import verify_current_decision_sources
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
        verification = verify_current_decision_sources(
            value["source_manifest"], root=ROOT
        )
        value["source_hash_verification"] = verification
        if not verification["valid"]:
            value["available"] = False
            value["status"] = "unavailable"
            value["ready_for_user_review"] = False
            value["production_actionable"] = False
            value["message"] = (
                "current market decision snapshot source drifted; rebuild required"
            )
            summary = value.setdefault("decision_summary", {})
            summary["headline"] = decision_headline(
                status="unavailable", ready_for_user_review=False
            )
            summary["blocking_conditions"] = list(
                dict.fromkeys(
                    summary.get("blocking_conditions", []) + verification["errors"]
                )
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
