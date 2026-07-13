from __future__ import annotations

from decision.current_market.explain import build_decision_summary, cash_explanation
from decision.current_market.freshness import evaluate_freshness


def build_current_market_decision(*, as_of: str, sources: dict) -> dict:
    diagnosis = sources.get("diagnosis", {})
    research = sources.get("research", {})
    shadow = sources.get("shadow", {})
    execution_report = sources.get("execution", {})
    market_state = _market_state(diagnosis)
    production_candidate = _production_candidate(diagnosis)
    research_allocation = _research_allocation(research, as_of)
    execution_shadow = _execution_shadow(shadow)
    execution_validation = _execution_validation(execution_report)
    freshness = evaluate_freshness(
        as_of=as_of,
        market_as_of=market_state.get("source_as_of"),
        research_date=research_allocation.get("allocation_date"),
        shadow=shadow,
        approval_integrity=sources.get("approval_integrity", {}),
        price_verification=sources.get("price_verification", {}),
    )
    cash_text = cash_explanation(execution_shadow.get("cash_breakdown", {}))
    violations = execution_shadow.get("constraint_checks", {}).get("violations", [])
    weights = execution_shadow.get("etf_weights", {})
    weight_sum_ok = abs(sum(float(value) for value in weights.values()) - 1.0) <= 0.000001
    core_available = all(
        (
            market_state.get("available"),
            research_allocation.get("available"),
            execution_shadow.get("available"),
        )
    )
    ready_for_user_review = bool(
        core_available
        and freshness.get("status") == "pass"
        and weight_sum_ok
        and not violations
    )
    decision_summary = build_decision_summary(
        market_state=market_state,
        shadow=shadow,
        execution=execution_validation,
        freshness=freshness,
        cash_text=cash_text,
    )
    status = (
        "stale"
        if freshness.get("status") == "stale"
        else "user_review_ready"
        if ready_for_user_review
        else "unavailable"
    )
    return {
        "available": core_available,
        "status": status,
        "ready_for_user_review": ready_for_user_review,
        "production_actionable": False,
        "as_of": as_of,
        "market_state": market_state,
        "production_candidate": production_candidate,
        "research_allocation": research_allocation,
        "execution_shadow": execution_shadow,
        "execution_validation": execution_validation,
        "comparison": {
            "mode": "side_by_side_only",
            "v11_vs_research_shadow": {
                "v11_allocation_available": production_candidate.get("allocation_available", False),
                "shadow_weights": weights,
                "automatic_selection": False,
            },
            "merged_portfolio_created": False,
        },
        "risk_summary": {
            "equity_weight": round(1.0 - float(weights.get("CASH", 0)), 10),
            "cash_weight": float(weights.get("CASH", 0)),
            "single_etf_limit": execution_shadow.get("constraint_checks", {}).get("single_etf_max", 0.35),
            "constraint_violations": violations,
            "key_risks": _key_risks(market_state, execution_validation, execution_shadow),
        },
        "cash_explanation": cash_text,
        "decision_summary": decision_summary,
        "data_freshness": freshness,
        "source_manifest": sources.get("source_manifest", {}),
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
    exposure = diagnosis.get("diagnosis", {}).get("exposure_analysis", {}).get("current", {})
    trend_score = exposure.get("trend_score")
    trend_state = (
        "positive" if trend_score is not None and trend_score >= 60
        else "weak" if trend_score is not None and trend_score <= 40
        else "mixed" if trend_score is not None
        else "unavailable"
    )
    risk_level = exposure.get("volatility_control", {}).get("volatility_state", "unavailable")
    evidence = list(value.get("evidence", []))
    evidence.extend(exposure.get("reason", []))
    return {
        "available": True,
        "regime": value["state"],
        "risk_level": risk_level,
        "trend_state": trend_state,
        "trend_score": trend_score,
        "confidence": value.get("confidence"),
        "evidence": evidence,
        "source": "reports/strategy_diagnosis_report.json:diagnosis.regime_v3",
        "source_as_of": source_as_of,
    }


def _production_candidate(diagnosis: dict) -> dict:
    readiness = diagnosis.get("diagnosis", {}).get("production_readiness", {})
    exposure = diagnosis.get("diagnosis", {}).get("exposure_analysis", {})
    source_as_of = diagnosis.get("dataset", {}).get("period", {}).get("end")
    return {
        "strategy": "V11_PRODUCTION_FUSION",
        "available": False,
        "allocation_available": False,
        "unchanged": True,
        "allocation": {},
        "risk_controls": exposure.get("current", {}) if exposure.get("version") == "v11" else {},
        "production_readiness": {
            "candidate": readiness.get("candidate"),
            "status": readiness.get("status"),
            "confidence": readiness.get("confidence"),
            "checks": readiness.get("checks", {}),
        },
        "source": "reports/strategy_diagnosis_report.json:diagnosis.production_readiness",
        "source_as_of": source_as_of,
        "message": "current V11 allocation source unavailable",
    }


def _research_allocation(research: dict, as_of: str) -> dict:
    rows = [row for row in research.get("monthly_allocations", []) if row.get("date", "") <= as_of]
    if not research.get("available") or not rows:
        return {"available": False, "status": "research_only", "message": "research allocation unavailable"}
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


def _execution_validation(report: dict) -> dict:
    decision = report.get("decision", {})
    metrics = report.get("metrics", {})
    mapping = report.get("mapping_summary", {})
    return {
        "ready": decision.get("ready_for_execution_validation") is True,
        "reasons": decision.get("reasons", []),
        "annual_return": metrics.get("annual_return"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "tradable_weight_coverage": mapping.get("tradable_weight_coverage"),
        "untradable_month_ratio": mapping.get("untradable_month_ratio"),
        "gate_thresholds_unchanged": True,
        "source": "reports/execution_backtest_report.json",
        "source_as_of": report.get("period", {}).get("end"),
    }


def _key_risks(market: dict, execution: dict, shadow: dict) -> list[str]:
    risks = [
        f"Market risk state: {market.get('risk_level', 'unavailable')}",
        *execution.get("reasons", []),
    ]
    if shadow.get("cash_breakdown", {}).get("research_only_cash", 0):
        risks.append("A research-only asset has no approved execution ETF and is held as cash.")
    if any(row.get("mapping_quality") == "medium" for row in shadow.get("mapping_explanations", [])):
        risks.append("At least one execution proxy is medium quality and broader than its research index.")
    return list(dict.fromkeys(risks))
