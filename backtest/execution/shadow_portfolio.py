from __future__ import annotations

from datetime import date

from backtest.execution.mapping_application import APPROVED_MAPPING_QUALITY


CASH_BREAKDOWN_KEYS = (
    "research_cash",
    "unmapped_cash",
    "research_only_cash",
    "rejected_proxy_cash",
    "low_quality_proxy_cash",
    "missing_price_cash",
)


def build_execution_aware_shadow_portfolio(
    research_report,
    mappings,
    execution_prices,
    provenance,
    decision_ledger,
    approval_record,
    approval_integrity=None,
    snapshot_integrity=None,
):
    allocations = research_report.get("monthly_allocations", [])
    if not research_report.get("available") or not allocations:
        return {"available": False, "message": "research allocation is unavailable"}
    if not provenance.get("provenance_verified"):
        return {"available": False, "message": "execution price provenance is not verified"}
    approval_integrity = approval_integrity or {}
    required_integrity = (
        "approval_record_verified",
        "package_verified",
        "mapping_verified",
        "ledger_verified",
        "seal_verified",
    )
    if not all(approval_integrity.get(field) is True for field in required_integrity):
        return {
            "available": False,
            "message": "execution mapping approval integrity is not verified",
            "errors": approval_integrity.get("errors", ["approval integrity missing"]),
        }
    snapshot_integrity = snapshot_integrity or {}
    if not snapshot_integrity.get("verified"):
        return {
            "available": False,
            "message": "shadow snapshot integrity is not verified",
            "errors": snapshot_integrity.get("errors", ["snapshot hashes missing"]),
        }

    period_end = research_report.get("period", {}).get("end")
    completed = [row for row in allocations if not period_end or row["date"] <= period_end]
    if not completed:
        return {"available": False, "message": "no completed research allocation"}
    source = max(completed, key=lambda row: row["date"])
    as_of_candidates = [
        value for value in (period_end, provenance.get("end")) if value
    ]
    if not as_of_candidates:
        return {"available": False, "message": "shadow data as-of date is unavailable"}
    data_as_of = min(as_of_candidates)

    by_mapping = {row.research_asset_id: row for row in mappings}
    by_decision = {
        row["research_asset_id"]: row
        for row in decision_ledger.get("decisions", [])
    }
    price_as_of_by_proxy = {}
    execution_weights = {}
    cash_breakdown = {key: 0.0 for key in CASH_BREAKDOWN_KEYS}
    explanations = []

    for research_asset_id, raw_weight in source.get("weights", {}).items():
        weight = float(raw_weight)
        if research_asset_id == "CASH":
            cash_breakdown["research_cash"] += weight
            explanations.append(
                {
                    "research_asset_id": research_asset_id,
                    "research_weight": weight,
                    "destination": "CASH",
                    "reason": "research_cash",
                }
            )
            continue

        mapping = by_mapping.get(research_asset_id)
        decision = by_decision.get(research_asset_id, {})
        decision_status = decision.get("status")
        proxy = mapping.primary_execution_proxy if mapping else None
        quality = mapping.mapping_quality if mapping else "none"
        cash_reason = _cash_reason(decision_status, quality, proxy)
        if not cash_reason:
            price_status = _latest_price_as_of(
                execution_prices.get(proxy, []), data_as_of
            )
            price_as_of_by_proxy[proxy] = price_status
            if not price_status["usable"]:
                cash_reason = "missing_price_cash"

        if cash_reason:
            cash_breakdown[cash_reason] += weight
            destination = "CASH"
            reason = cash_reason
        else:
            execution_weights[proxy] = execution_weights.get(proxy, 0.0) + weight
            destination = proxy
            reason = "approved_or_registered_execution_mapping"
        explanations.append(
            {
                "research_asset_id": research_asset_id,
                "research_weight": round(weight, 10),
                "destination": destination,
                "mapping_quality": quality,
                "decision_status": decision_status,
                "reason": reason,
                "production_approved": False,
            }
        )

    cash_breakdown = {
        key: round(cash_breakdown[key], 10) for key in CASH_BREAKDOWN_KEYS
    }
    cash_total = round(sum(cash_breakdown.values()), 10)
    if cash_total:
        execution_weights["CASH"] = cash_total
    execution_weights = {
        key: round(value, 10) for key, value in sorted(execution_weights.items())
    }
    violations = [
        {"asset_id": asset_id, "weight": weight, "limit": 0.35}
        for asset_id, weight in execution_weights.items()
        if asset_id != "CASH" and weight > 0.35
    ]
    total = round(sum(execution_weights.values()), 10)
    if abs(total - 1.0) > 0.000001:
        violations.append(
            {"type": "weight_sum", "weight": total, "expected": 1.0}
        )

    return {
        "available": True,
        "status": "shadow_only",
        "production_approved": False,
        "source_strategy": research_report.get("strategy"),
        "source_allocation_date": source["date"],
        "data_as_of": data_as_of,
        "research_weights": source.get("weights", {}),
        "execution_weights": execution_weights,
        "cash_breakdown": cash_breakdown,
        "mapping_explanations": explanations,
        "constraint_checks": {
            "single_etf_max": 0.35,
            "weight_sum": total,
            "violations": violations,
        },
        "data_provenance": {
            "provider": provenance.get("provider"),
            "return_basis": provenance.get("return_basis"),
            "provenance_verified": provenance.get("provenance_verified"),
            "dataset_generated_at": provenance.get("dataset_generated_at"),
            "asset_count": provenance.get("asset_count"),
        },
        "approval_integrity": approval_integrity,
        "snapshot_integrity": snapshot_integrity,
        "price_as_of_by_proxy": dict(sorted(price_as_of_by_proxy.items())),
        "approved_mapping_records": [
            {
                "research_asset_id": approval_record.get("research_asset_id"),
                "approved_proxy": approval_record.get("approved_proxy"),
                "approved_mapping_quality": approval_record.get(
                    "approved_mapping_quality"
                ),
                "approval_record": "execution_mapping_approval_record.json",
                "production_approved": False,
            }
        ],
        "frozen_research_only_assets": sorted(
            row["research_asset_id"]
            for row in decision_ledger.get("decisions", [])
            if row.get("status") == "research_only"
        ),
        "rejected_proxy_assets": sorted(
            row["research_asset_id"]
            for row in decision_ledger.get("decisions", [])
            if row.get("status") == "rejected_proxy"
        ),
        "warnings": [
            "This is an experimental execution-aware shadow allocation. It is not a production portfolio or trading instruction.",
            "V11 remains the existing production candidate and is not replaced by this shadow allocation.",
            "Weights are research ratios only; no orders, quantities, or target prices are produced.",
        ],
    }


def _cash_reason(decision_status, quality, proxy):
    if decision_status == "research_only":
        return "research_only_cash"
    if decision_status == "rejected_proxy":
        return "rejected_proxy_cash"
    if quality == "low":
        return "low_quality_proxy_cash"
    if not proxy or quality == "none":
        return "unmapped_cash"
    if quality not in {"high", APPROVED_MAPPING_QUALITY}:
        return "unmapped_cash"
    return None


def _latest_price_as_of(rows, requested_as_of):
    eligible = sorted(row.date for row in rows if row.date <= requested_as_of)
    actual = eligible[-1] if eligible else None
    staleness = (
        (date.fromisoformat(requested_as_of) - date.fromisoformat(actual)).days
        if actual
        else None
    )
    return {
        "requested_as_of": requested_as_of,
        "actual_price_date": actual,
        "staleness_calendar_days": staleness,
        "usable": actual is not None and staleness <= 5,
    }
