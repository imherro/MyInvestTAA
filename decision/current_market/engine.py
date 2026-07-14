from __future__ import annotations

from datetime import UTC, date, datetime
import math
import re

from decision.current_market.explain import build_cash_explanation, build_decision_summary
from decision.current_market.freshness import evaluate_freshness
from decision.current_market.instrument_ids import normalize_weight_map
from decision.current_market.source_policy import (
    sha256_file,
    verify_current_decision_source_entry,
    verify_current_decision_sources,
)
from engine.asset_registry.loader import ROOT


CURRENT_SNAPSHOT_MODE = "current_decision_with_lagged_market_data"
HISTORICAL_SNAPSHOT_MODE = "historical_snapshot"


def build_current_market_decision(
    *,
    sources: dict,
    market_data_as_of: str | None = None,
    decision_date: str | None = None,
    snapshot_mode: str = CURRENT_SNAPSHOT_MODE,
    as_of: str | None = None,
    generated_at: str | None = None,
) -> dict:
    market_data_as_of = market_data_as_of or as_of
    if not market_data_as_of:
        raise ValueError("market_data_as_of is required")
    if snapshot_mode not in {CURRENT_SNAPSHOT_MODE, HISTORICAL_SNAPSHOT_MODE}:
        raise ValueError("unsupported snapshot_mode")

    source_manifest = sources.get("source_manifest", {})
    governance_state_as_of = _governance_state_as_of(source_manifest)
    decision_date = decision_date or governance_state_as_of or market_data_as_of
    diagnosis = sources.get("diagnosis", {})
    research = sources.get("research", {})
    shadow = sources.get("shadow", {})
    execution_report = sources.get("execution", {})

    market_state = _market_state(diagnosis)
    production_candidate = _production_candidate(
        diagnosis,
        sources.get("v11_allocation", {}),
        snapshot_present=source_manifest.get("v11_current_allocation", {}).get(
            "available"
        )
        is True,
    )
    research_allocation = _research_allocation(research, market_data_as_of)
    execution_shadow = _execution_shadow(shadow)
    weights = execution_shadow.get("etf_weights", {})
    comparison = _strategy_comparison(
        production_candidate.get("allocation", {}),
        weights,
        sources.get("instrument_aliases", {}),
        v11_allocation_available=production_candidate.get(
            "current_allocation_available", False
        ),
    )
    source_hash_verification = verify_current_decision_sources(source_manifest)
    if sources.get("source_path_overrides"):
        source_hash_verification = verify_current_decision_sources(
            source_manifest,
            path_overrides=sources["source_path_overrides"],
        )
    execution_validation = _execution_validation(
        execution_report,
        sources.get("gate_policy", {}),
        source_manifest.get("execution_gate_policy", {}),
    )
    freshness = evaluate_freshness(
        market_data_as_of=market_data_as_of,
        decision_date=decision_date,
        governance_state_as_of=governance_state_as_of,
        snapshot_mode=snapshot_mode,
        market_as_of=market_state.get("source_as_of"),
        research_date=research_allocation.get("allocation_date"),
        research_source_as_of=research_allocation.get("source_as_of"),
        execution_source_as_of=execution_validation.get("source_as_of"),
        v11_allocation_source_as_of=production_candidate.get(
            "allocation_source_as_of"
        ),
        shadow=shadow,
        approval_integrity=sources.get("approval_integrity", {}),
        price_verification=sources.get("price_verification", {}),
    )

    cash_weight = float(weights.get("CASH", 0))
    cash = build_cash_explanation(
        execution_shadow.get("cash_breakdown", {}),
        execution_shadow.get("mapping_explanations", []),
        cash_weight,
    )
    violations = execution_shadow.get("constraint_checks", {}).get("violations", [])
    weight_sum_ok = abs(sum(float(value) for value in weights.values()) - 1.0) <= 0.000001
    evidence_complete = all(
        (
            market_state.get("available"),
            production_candidate.get("boundary_verified"),
            production_candidate.get("snapshot_valid_or_missing"),
            research_allocation.get("available"),
            execution_shadow.get("available"),
            execution_validation.get("available"),
            execution_validation.get("evidence_complete"),
            source_hash_verification.get("valid"),
            comparison.get("identifier_normalization_verified"),
        )
    )
    ready_for_user_review = bool(
        evidence_complete
        and freshness.get("status") == "pass"
        and freshness.get("temporal_status") == "pass"
        and weight_sum_ok
        and not violations
        and cash.get("reconciled")
    )
    review_blockers = _review_blockers(
        production_candidate=production_candidate,
        execution_validation=execution_validation,
        source_hash_verification=source_hash_verification,
        freshness=freshness,
        weight_sum_ok=weight_sum_ok,
        violations=violations,
        cash=cash,
        comparison=comparison,
    )
    status = (
        "stale"
        if freshness.get("status") == "stale"
        else "user_review_ready"
        if ready_for_user_review
        else "unavailable"
    )
    decision_summary = build_decision_summary(
        market_state=market_state,
        shadow=shadow,
        execution=execution_validation,
        freshness=freshness,
        cash_text=cash["text"],
        ready_for_user_review=ready_for_user_review,
        status=status,
        evidence_blockers=review_blockers,
    )
    return {
        "available": evidence_complete,
        "status": status,
        "ready_for_user_review": ready_for_user_review,
        "production_actionable": False,
        "as_of": market_data_as_of,
        "decision_date": decision_date,
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "market_data_as_of": market_data_as_of,
        "governance_state_as_of": governance_state_as_of,
        "snapshot_mode": snapshot_mode,
        "market_state": market_state,
        "production_candidate": production_candidate,
        "research_allocation": research_allocation,
        "execution_shadow": execution_shadow,
        "execution_validation": execution_validation,
        "comparison": comparison,
        "risk_summary": {
            "equity_weight": round(1.0 - cash_weight, 10),
            "cash_weight": cash_weight,
            "single_etf_limit": execution_shadow.get("constraint_checks", {}).get(
                "single_etf_max", 0.35
            ),
            "constraint_violations": violations,
            "key_risks": _key_risks(
                market_state, execution_validation, execution_shadow
            ),
        },
        "cash_explanation": cash["text"],
        "cash_explanation_components": cash["components"],
        "cash_reconciliation": {
            key: cash[key]
            for key in ("total_cash_weight", "component_weight_sum", "reconciled")
        },
        "decision_summary": decision_summary,
        "data_freshness": freshness,
        "source_manifest": source_manifest,
        "source_hash_verification": source_hash_verification,
        "warnings": [
            "This report is for user review only and is not a production trading instruction.",
            "V11 remains unchanged and is not replaced by the Research or Shadow allocation.",
            "No orders, quantities, shares, target prices, or merged portfolio are produced.",
        ],
    }


def _market_state(diagnosis: dict) -> dict:
    if not diagnosis.get("available"):
        return {"available": False, "message": "current market state source unavailable"}
    value = diagnosis.get("diagnosis", {}).get("regime_v3", {})
    source_as_of = diagnosis.get("dataset", {}).get("period", {}).get("end")
    if not value.get("state") or not source_as_of:
        return {"available": False, "message": "current market state source unavailable"}
    exposure = diagnosis.get("diagnosis", {}).get("exposure_analysis", {}).get(
        "current", {}
    )
    trend_score = exposure.get("trend_score")
    trend_state = (
        "positive"
        if trend_score is not None and trend_score >= 60
        else "weak"
        if trend_score is not None and trend_score <= 40
        else "mixed"
        if trend_score is not None
        else "unavailable"
    )
    evidence = list(value.get("evidence", []))
    evidence.extend(exposure.get("reason", []))
    return {
        "available": True,
        "regime": value["state"],
        "risk_level": exposure.get("volatility_control", {}).get(
            "volatility_state", "unavailable"
        ),
        "trend_state": trend_state,
        "trend_score": trend_score,
        "confidence": value.get("confidence"),
        "evidence": evidence,
        "source": "reports/strategy_diagnosis_report.json:diagnosis.regime_v3",
        "source_as_of": source_as_of,
    }


def _production_candidate(
    diagnosis: dict,
    allocation_snapshot: dict,
    *,
    snapshot_present: bool,
) -> dict:
    readiness = diagnosis.get("diagnosis", {}).get("production_readiness", {})
    exposure = diagnosis.get("diagnosis", {}).get("exposure_analysis", {})
    source_as_of = diagnosis.get("dataset", {}).get("period", {}).get("end")
    strategy = readiness.get("candidate")
    metadata_available = bool(
        diagnosis.get("available")
        and strategy == "V11_PRODUCTION_FUSION"
        and readiness.get("status")
    )
    integrity = allocation_snapshot.get("source_integrity", {})
    expected_payload_hash = integrity.get("snapshot_payload_hash")
    actual_payload_hash = integrity.get("actual_snapshot_payload_hash")
    payload_hash_verified = bool(
        isinstance(expected_payload_hash, str)
        and re.fullmatch(r"[0-9a-f]{64}", expected_payload_hash)
        and actual_payload_hash == expected_payload_hash
    )
    allocation_available = bool(
        allocation_snapshot.get("available")
        and allocation_snapshot.get("strategy") == strategy
        and isinstance(allocation_snapshot.get("allocation"), dict)
        and allocation_snapshot.get("allocation")
        and allocation_snapshot.get("production_actionable") is False
        and allocation_snapshot.get("trading_instruction") is False
        and integrity.get("verified") is True
        and integrity.get("semantic_verified") is True
        and payload_hash_verified
        and not allocation_snapshot.get("constraint_checks", {}).get("violations")
    )
    allocation = allocation_snapshot.get("allocation", {}) if allocation_available else {}
    snapshot_valid_or_missing = bool(not snapshot_present or allocation_available)
    boundary_verified = bool(
        metadata_available
        and strategy
        and not allocation_snapshot.get("shadow_source")
        and snapshot_valid_or_missing
    )
    unchanged = bool(boundary_verified and readiness.get("candidate") == strategy)
    return {
        "strategy": strategy or "V11_PRODUCTION_FUSION",
        "available": metadata_available,
        "candidate_metadata_available": metadata_available,
        "allocation_available": allocation_available,
        "current_allocation_available": allocation_available,
        "boundary_verified": boundary_verified,
        "snapshot_present": snapshot_present,
        "snapshot_integrity_verified": allocation_available,
        "snapshot_semantic_verified": integrity.get("semantic_verified") is True,
        "snapshot_payload_hash_verified": payload_hash_verified,
        "snapshot_valid_or_missing": snapshot_valid_or_missing,
        "unchanged": unchanged,
        "allocation": allocation,
        "allocation_percent": allocation_snapshot.get("allocation_percent", {})
        if allocation_available
        else {},
        "equity_weight": allocation_snapshot.get("equity_weight")
        if allocation_available
        else None,
        "cash_weight": allocation_snapshot.get("cash_weight")
        if allocation_available
        else None,
        "selected_assets": allocation_snapshot.get("selected_assets", [])
        if allocation_available
        else [],
        "production_actionable": False,
        "risk_controls": exposure.get("current", {})
        if exposure.get("version") == "v11"
        else {},
        "production_readiness": {
            "candidate": readiness.get("candidate"),
            "status": readiness.get("status"),
            "confidence": readiness.get("confidence"),
            "checks": readiness.get("checks", {}),
        },
        "source": "reports/strategy_diagnosis_report.json:diagnosis.production_readiness",
        "source_as_of": source_as_of,
        "allocation_source": allocation_snapshot.get("report_path")
        if allocation_available
        else None,
        "allocation_source_as_of": allocation_snapshot.get("as_of")
        if allocation_available
        else None,
        "allocation_integrity": allocation_snapshot.get("source_integrity", {})
        if snapshot_present
        else {},
        "release_artifact_dependency": allocation_snapshot.get(
            "release_artifact_dependency"
        ),
        "message": (
            None
            if allocation_available
            else "current V11 allocation snapshot invalid"
            if snapshot_present
            else "current V11 allocation source unavailable"
        ),
    }


def _research_allocation(research: dict, market_data_as_of: str) -> dict:
    rows = [
        row
        for row in research.get("monthly_allocations", [])
        if row.get("date", "") <= market_data_as_of
    ]
    if not research.get("available") or not rows:
        return {
            "available": False,
            "status": "research_only",
            "message": "research allocation unavailable",
        }
    latest = max(rows, key=lambda row: row["date"])
    return {
        "available": True,
        "strategy": research.get("strategy"),
        "allocation_date": latest["date"],
        "weights": latest.get("weights", {}),
        "status": "research_only",
        "source": "reports/research_backtest_report.json:monthly_allocations",
        "source_as_of": research.get("period", {}).get("end"),
    }


def _execution_shadow(shadow: dict) -> dict:
    return {
        "available": shadow.get("available") is True,
        "status": shadow.get("status"),
        "production_approved": False,
        "data_as_of": shadow.get("data_as_of"),
        "etf_weights": shadow.get("execution_weights", {}),
        "cash_breakdown": shadow.get("cash_breakdown", {}),
        "mapping_explanations": shadow.get("mapping_explanations", []),
        "constraint_checks": shadow.get("constraint_checks", {}),
        "snapshot_integrity": shadow.get("snapshot_integrity", {}),
        "approval_integrity": shadow.get("approval_integrity", {}),
        "price_as_of_by_proxy": shadow.get("price_as_of_by_proxy", {}),
        "source": "reports/execution_aware_shadow_portfolio.json",
        "source_as_of": shadow.get("data_as_of"),
    }


def _execution_validation(report: dict, gate_policy: dict, policy_source: dict) -> dict:
    evidence = validate_execution_decision_evidence(report, gate_policy, policy_source)
    decision = report.get("decision", {})
    metrics = report.get("metrics", {})
    mapping = report.get("mapping_summary", {})
    policy_fields = (
        "policy_id",
        "tradable_weight_coverage_min",
        "untradable_month_ratio_max",
        "max_drawdown_min",
        "sharpe_min",
        "annual_return_gap_min",
        "source",
    )
    return {
        "available": evidence["valid"],
        "ready": decision.get("ready_for_execution_validation") is True,
        "reasons": decision.get("reasons", [])
        if isinstance(decision.get("reasons"), list)
        else [],
        "metrics_available": evidence["metrics_available"],
        "evidence_complete": evidence["valid"],
        "policy_schema_verified": evidence["policy_schema_verified"],
        "semantic_errors": evidence["errors"],
        "annual_return": metrics.get("annual_return"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "tradable_weight_coverage": mapping.get("tradable_weight_coverage"),
        "untradable_month_ratio": mapping.get("untradable_month_ratio"),
        "gate_policy": {
            **{field: gate_policy.get(field) for field in policy_fields},
            "policy_hash": policy_source.get("sha256"),
            "manifest_source": policy_source.get("path"),
            "available": evidence["policy_schema_verified"],
            "policy_schema_verified": evidence["policy_schema_verified"],
            "policy_hash_verified": evidence["policy_hash_verified"],
            "execution_engine_source_hash": evidence[
                "execution_engine_source_hash"
            ],
        },
        "source": "reports/execution_backtest_report.json",
        "source_as_of": report.get("period", {}).get("end"),
        "message": None
        if evidence["valid"]
        else "execution validation report unavailable or semantically incomplete",
    }


def validate_execution_decision_evidence(
    report: dict,
    gate_policy: dict,
    policy_source: dict,
) -> dict:
    errors: list[str] = []
    if report.get("available") is not True:
        errors.append("execution report unavailable")

    decision = report.get("decision", {})
    ready = decision.get("ready_for_execution_validation")
    reasons = decision.get("reasons")
    if not isinstance(ready, bool):
        errors.append("execution decision ready_for_execution_validation must be boolean")
    if not isinstance(reasons, list):
        errors.append("execution decision reasons must be list[str]")
    else:
        if any(not isinstance(reason, str) for reason in reasons):
            errors.append("execution decision reason must be a string")
        if any(isinstance(reason, str) and not reason.strip() for reason in reasons):
            errors.append("execution decision reason must be non-empty")
        if ready is True and reasons:
            errors.append("execution decision ready=true requires empty reasons")
        if ready is False and not reasons:
            errors.append("execution decision ready=false requires non-empty reasons")

    metrics = report.get("metrics", {})
    mapping = report.get("mapping_summary", {})
    metric_errors: list[str] = []
    for field in ("annual_return", "max_drawdown", "sharpe"):
        if not _is_finite_number(metrics.get(field)):
            metric_errors.append(f"execution metric {field} must be finite")
    for field in ("tradable_weight_coverage", "untradable_month_ratio"):
        value = mapping.get(field)
        if not _is_finite_number(value):
            metric_errors.append(f"execution metric {field} must be finite")
        elif not 0 <= float(value) <= 1:
            metric_errors.append(f"execution metric {field} must be between 0 and 1")
    errors.extend(metric_errors)

    period = report.get("period", {})
    start = period.get("start")
    end = period.get("end")
    start_date = _execution_date(start, "execution period start", errors)
    end_date = _execution_date(end, "execution period end", errors)
    if start_date and end_date and start_date > end_date:
        errors.append("execution period start must not be after end")

    policy_errors: list[str] = []
    policy_id = gate_policy.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id.strip():
        policy_errors.append("execution gate policy policy_id must be non-empty")
    for field in (
        "tradable_weight_coverage_min",
        "untradable_month_ratio_max",
        "max_drawdown_min",
        "sharpe_min",
        "annual_return_gap_min",
    ):
        if not _is_finite_number(gate_policy.get(field)):
            policy_errors.append(f"execution gate policy {field} must be finite")
    for field in ("tradable_weight_coverage_min", "untradable_month_ratio_max"):
        value = gate_policy.get(field)
        if _is_finite_number(value) and not 0 <= float(value) <= 1:
            policy_errors.append(f"execution gate policy {field} must be between 0 and 1")
    if gate_policy.get("source") != "backtest/execution/engine.py:_decision":
        policy_errors.append("execution gate policy source is invalid")

    policy_source_errors = verify_current_decision_source_entry(
        "execution_gate_policy", policy_source
    )
    errors.extend(policy_errors)
    errors.extend(policy_source_errors)
    policy_schema_verified = not policy_errors and not policy_source_errors
    execution_engine = ROOT / "backtest" / "execution" / "engine.py"
    return {
        "valid": not errors,
        "metrics_available": not metric_errors,
        "policy_schema_verified": policy_schema_verified,
        "policy_hash_verified": not policy_source_errors,
        "execution_engine_source_hash": sha256_file(execution_engine)
        if execution_engine.exists()
        else None,
        "errors": errors,
    }


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _execution_date(
    value: object,
    label: str,
    errors: list[str],
) -> date | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} is required")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be a valid ISO date")
        return None


def _governance_state_as_of(manifest: dict) -> str | None:
    values = [
        row.get("source_as_of")
        for row in manifest.values()
        if row.get("temporal_role") == "governance" and row.get("source_as_of")
    ]
    return max(values) if values else None


def _review_blockers(
    *,
    production_candidate: dict,
    execution_validation: dict,
    source_hash_verification: dict,
    freshness: dict,
    weight_sum_ok: bool,
    violations: list,
    cash: dict,
    comparison: dict,
) -> list[str]:
    blockers = []
    if not production_candidate.get("boundary_verified"):
        blockers.append("V11 and Shadow boundary is not verified")
    if not production_candidate.get("snapshot_valid_or_missing"):
        blockers.append("V11 current allocation snapshot is present but invalid")
    if not execution_validation.get("available"):
        blockers.append("execution validation report unavailable")
        blockers.extend(execution_validation.get("semantic_errors", []))
    elif not execution_validation.get("evidence_complete"):
        blockers.append("execution validation evidence is incomplete")
    blockers.extend(source_hash_verification.get("errors", []))
    blockers.extend(freshness.get("temporal_errors", []))
    if not weight_sum_ok:
        blockers.append("execution weights do not sum to one")
    if violations:
        blockers.append("execution shadow has constraint violations")
    if not cash.get("reconciled"):
        blockers.append("cash explanation components do not reconcile to Shadow cash")
    if not comparison.get("identifier_normalization_verified"):
        blockers.append("instrument identifier normalization failed")
        blockers.extend(comparison.get("identifier_errors", []))
    return blockers


def _key_risks(market: dict, execution: dict, shadow: dict) -> list[str]:
    risks = [
        f"Market risk state: {market.get('risk_level', 'unavailable')}",
        *execution.get("reasons", []),
    ]
    if shadow.get("cash_breakdown", {}).get("research_only_cash", 0):
        risks.append("At least one research-only asset has no approved execution ETF.")
    if any(
        row.get("mapping_quality") == "medium"
        for row in shadow.get("mapping_explanations", [])
    ):
        risks.append(
            "At least one execution proxy is medium quality and broader than its research index."
        )
    return list(dict.fromkeys(risks))


def _weight_differences(v11: dict, shadow: dict) -> dict:
    return {
        asset_id: round(float(v11.get(asset_id, 0)) - float(shadow.get(asset_id, 0)), 12)
        for asset_id in sorted(set(v11) | set(shadow))
    }


def _strategy_comparison(
    v11_weights: dict,
    shadow_weights: dict,
    alias_registry: dict,
    *,
    v11_allocation_available: bool,
) -> dict:
    v11_normalized = normalize_weight_map(v11_weights, alias_registry)
    shadow_normalized = normalize_weight_map(shadow_weights, alias_registry)
    errors = list(
        dict.fromkeys(
            v11_normalized.get("errors", [])
            + shadow_normalized.get("errors", [])
        )
    )
    verified = bool(
        v11_normalized.get("verified") and shadow_normalized.get("verified")
    )
    v11_canonical = v11_normalized.get("weights", {}) if verified else {}
    shadow_canonical = shadow_normalized.get("weights", {}) if verified else {}
    normalization_map = {
        "v11": v11_normalized.get("normalization_map", {}),
        "shadow": shadow_normalized.get("normalization_map", {}),
    }
    return {
        "mode": "side_by_side_only",
        "identifier_namespace": alias_registry.get("namespace"),
        "identifier_normalization_verified": verified,
        "v11_allocation_available": v11_allocation_available,
        "v11_original_weights": v11_weights,
        "v11_canonical_weights": v11_canonical,
        "shadow_canonical_weights": shadow_canonical,
        "weight_differences": _weight_differences(
            v11_canonical, shadow_canonical
        )
        if verified
        else {},
        "normalization_map": normalization_map,
        "unresolved_v11_ids": v11_normalized.get("unresolved_ids", []),
        "unresolved_shadow_ids": shadow_normalized.get("unresolved_ids", []),
        "identifier_errors": errors,
        "v11_vs_research_shadow": {
            "v11_allocation_available": v11_allocation_available,
            "shadow_weights": shadow_canonical,
            "automatic_selection": False,
        },
        "automatic_selection": False,
        "merged_portfolio_created": False,
    }
