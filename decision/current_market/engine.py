from __future__ import annotations

from datetime import UTC, datetime

from decision.current_market.explain import build_cash_explanation, build_decision_summary
from decision.current_market.freshness import evaluate_freshness


CURRENT_SNAPSHOT_MODE = "current_decision_with_lagged_market_data"
HISTORICAL_SNAPSHOT_MODE = "historical_snapshot"


def build_current_market_decision(
    *,
    sources: dict,
    market_data_as_of: str | None = None,
    decision_date: str | None = None,
    snapshot_mode: str = CURRENT_SNAPSHOT_MODE,
    as_of: str | None = None,
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
        diagnosis, sources.get("v11_allocation", {})
    )
    research_allocation = _research_allocation(research, market_data_as_of)
    execution_shadow = _execution_shadow(shadow)
    execution_validation = _execution_validation(
        execution_report,
        sources.get("gate_policy", {}),
        source_manifest.get("execution_gate_policy", {}),
    )
    source_hash_verification = _source_hash_status(source_manifest)
    freshness = evaluate_freshness(
        market_data_as_of=market_data_as_of,
        decision_date=decision_date,
        governance_state_as_of=governance_state_as_of,
        snapshot_mode=snapshot_mode,
        market_as_of=market_state.get("source_as_of"),
        research_date=research_allocation.get("allocation_date"),
        research_source_as_of=research_allocation.get("source_as_of"),
        execution_source_as_of=execution_validation.get("source_as_of"),
        shadow=shadow,
        approval_integrity=sources.get("approval_integrity", {}),
        price_verification=sources.get("price_verification", {}),
    )

    weights = execution_shadow.get("etf_weights", {})
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
            research_allocation.get("available"),
            execution_shadow.get("available"),
            execution_validation.get("available"),
            execution_validation.get("evidence_complete"),
            source_hash_verification.get("valid"),
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
    decision_summary = build_decision_summary(
        market_state=market_state,
        shadow=shadow,
        execution=execution_validation,
        freshness=freshness,
        cash_text=cash["text"],
    )
    review_blockers = _review_blockers(
        production_candidate=production_candidate,
        execution_validation=execution_validation,
        source_hash_verification=source_hash_verification,
        freshness=freshness,
        weight_sum_ok=weight_sum_ok,
        violations=violations,
        cash=cash,
    )
    decision_summary["blocking_conditions"] = list(
        dict.fromkeys(decision_summary["blocking_conditions"] + review_blockers)
    )
    status = (
        "stale"
        if freshness.get("status") == "stale"
        else "user_review_ready"
        if ready_for_user_review
        else "unavailable"
    )
    return {
        "available": evidence_complete,
        "status": status,
        "ready_for_user_review": ready_for_user_review,
        "production_actionable": False,
        "as_of": market_data_as_of,
        "decision_date": decision_date,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "market_data_as_of": market_data_as_of,
        "governance_state_as_of": governance_state_as_of,
        "snapshot_mode": snapshot_mode,
        "market_state": market_state,
        "production_candidate": production_candidate,
        "research_allocation": research_allocation,
        "execution_shadow": execution_shadow,
        "execution_validation": execution_validation,
        "comparison": {
            "mode": "side_by_side_only",
            "v11_vs_research_shadow": {
                "v11_allocation_available": production_candidate.get(
                    "current_allocation_available", False
                ),
                "shadow_weights": weights,
                "automatic_selection": False,
            },
            "merged_portfolio_created": False,
        },
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


def _production_candidate(diagnosis: dict, allocation_snapshot: dict) -> dict:
    readiness = diagnosis.get("diagnosis", {}).get("production_readiness", {})
    exposure = diagnosis.get("diagnosis", {}).get("exposure_analysis", {})
    source_as_of = diagnosis.get("dataset", {}).get("period", {}).get("end")
    strategy = readiness.get("candidate")
    metadata_available = bool(
        diagnosis.get("available")
        and strategy == "V11_PRODUCTION_FUSION"
        and readiness.get("status")
    )
    allocation_available = bool(
        allocation_snapshot.get("available")
        and allocation_snapshot.get("strategy") == strategy
        and isinstance(allocation_snapshot.get("allocation"), dict)
        and allocation_snapshot.get("allocation")
    )
    allocation = allocation_snapshot.get("allocation", {}) if allocation_available else {}
    boundary_verified = bool(metadata_available and strategy and not allocation_snapshot.get("shadow_source"))
    unchanged = bool(boundary_verified and readiness.get("candidate") == strategy)
    return {
        "strategy": strategy or "V11_PRODUCTION_FUSION",
        "available": metadata_available,
        "candidate_metadata_available": metadata_available,
        "allocation_available": allocation_available,
        "current_allocation_available": allocation_available,
        "boundary_verified": boundary_verified,
        "unchanged": unchanged,
        "allocation": allocation,
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
        "message": None
        if allocation_available
        else "current V11 allocation source unavailable",
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
    decision = report.get("decision", {})
    metrics = report.get("metrics", {})
    mapping = report.get("mapping_summary", {})
    metric_fields = ("annual_return", "max_drawdown", "sharpe")
    mapping_fields = ("tradable_weight_coverage", "untradable_month_ratio")
    metrics_available = all(
        isinstance(metrics.get(field), (int, float)) for field in metric_fields
    ) and all(isinstance(mapping.get(field), (int, float)) for field in mapping_fields)
    decision_available = isinstance(
        decision.get("ready_for_execution_validation"), bool
    ) and isinstance(decision.get("reasons"), list)
    policy_available = bool(
        gate_policy.get("available")
        and policy_source.get("available")
        and policy_source.get("sha256")
    )
    available = bool(report.get("available") and decision_available and metrics_available)
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
        "available": available,
        "ready": decision.get("ready_for_execution_validation") is True,
        "reasons": decision.get("reasons", []) if decision_available else [],
        "metrics_available": metrics_available,
        "evidence_complete": bool(available and policy_available),
        "annual_return": metrics.get("annual_return"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "tradable_weight_coverage": mapping.get("tradable_weight_coverage"),
        "untradable_month_ratio": mapping.get("untradable_month_ratio"),
        "gate_policy": {
            **{field: gate_policy.get(field) for field in policy_fields},
            "policy_hash": policy_source.get("sha256"),
            "manifest_source": policy_source.get("path"),
            "available": policy_available,
        },
        "source": "reports/execution_backtest_report.json",
        "source_as_of": report.get("period", {}).get("end"),
        "message": None if available else "execution validation report unavailable or incomplete",
    }


def _source_hash_status(manifest: dict) -> dict:
    required = [row for row in manifest.values() if row.get("required")]
    errors = []
    for row in required:
        if not row.get("available"):
            errors.append(f"required source unavailable: {row.get('source')}")
        elif not isinstance(row.get("sha256"), str) or len(row["sha256"]) != 64:
            errors.append(f"required source hash invalid: {row.get('source')}")
    return {
        "valid": not errors,
        "required_count": len(required),
        "available_required_count": sum(bool(row.get("available")) for row in required),
        "errors": errors,
    }


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
) -> list[str]:
    blockers = []
    if not production_candidate.get("boundary_verified"):
        blockers.append("V11 and Shadow boundary is not verified")
    if not execution_validation.get("available"):
        blockers.append("execution validation report unavailable")
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
