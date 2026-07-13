from __future__ import annotations

import calendar
from datetime import date

from decision.current_market.models import FreshnessCheck


def evaluate_freshness(
    *,
    market_data_as_of: str,
    decision_date: str,
    governance_state_as_of: str | None,
    snapshot_mode: str,
    market_as_of: str | None,
    research_date: str | None,
    research_source_as_of: str | None,
    execution_source_as_of: str | None,
    shadow: dict,
    approval_integrity: dict,
    price_verification: dict,
) -> dict:
    target = date.fromisoformat(market_data_as_of)
    market = _dated_check(target, market_as_of, 7, "market data")
    proxy_checks = {}
    for proxy, row in shadow.get("price_as_of_by_proxy", {}).items():
        actual = row.get("actual_price_date")
        proxy_checks[proxy] = _dated_check(target, actual, 5, f"ETF price {proxy}")
    etf_stale = not proxy_checks or any(row["stale"] for row in proxy_checks.values())
    approval_validation = approval_integrity.get("validation", {})
    approval_verified = all(
        approval_validation.get(field) is True
        for field in (
            "approval_record_verified",
            "package_verified",
            "mapping_verified",
            "ledger_verified",
            "seal_verified",
        )
    )
    shadow_verified = shadow.get("snapshot_integrity", {}).get("verified") is True
    price_files_verified = price_verification.get("provenance_verified") is True
    research = {
        "allocation_date": research_date,
        "expected_cadence": "monthly",
        "schedule_policy": "last_completed_monthly_rebalance",
        "next_rebalance_estimate": _next_month_end(research_date),
        "estimate_basis": "calendar_month_end",
        "confirmed_trading_date": False,
        "stale": False,
        "message": "Monthly allocation date is reported separately and is not treated as daily data.",
    }
    errors = []
    if market["stale"]:
        errors.append(market["message"])
    if etf_stale:
        errors.append("one or more ETF price snapshots are stale or unavailable")
    if not approval_verified:
        errors.append("approval integrity is not verified")
    if not shadow_verified:
        errors.append("shadow snapshot integrity is not verified")
    if not price_files_verified:
        errors.extend(price_verification.get("errors", ["ETF price files are not verified"]))
    temporal_errors = _temporal_errors(
        market_data_as_of=market_data_as_of,
        decision_date=decision_date,
        governance_state_as_of=governance_state_as_of,
        snapshot_mode=snapshot_mode,
        research_source_as_of=research_source_as_of,
        execution_source_as_of=execution_source_as_of,
    )
    return {
        "status": "pass" if not errors else "stale",
        "market_data_as_of": market_data_as_of,
        "decision_date": decision_date,
        "governance_state_as_of": governance_state_as_of,
        "snapshot_mode": snapshot_mode,
        "market_data": market,
        "etf_prices": {
            "stale": etf_stale,
            "checks": proxy_checks,
            "actual_files_verified": price_files_verified,
            "verification_errors": price_verification.get("errors", []),
        },
        "research_allocation": research,
        "approval_integrity_verified": approval_verified,
        "shadow_snapshot_verified": shadow_verified,
        "errors": list(dict.fromkeys(errors)),
        "temporal_status": "pass" if not temporal_errors else "invalid",
        "temporal_errors": temporal_errors,
    }


def _dated_check(target: date, source_as_of: str | None, limit: int, label: str) -> dict:
    if not source_as_of:
        return FreshnessCheck(None, None, limit, True, f"{label} as-of date is unavailable").as_dict()
    source = date.fromisoformat(source_as_of)
    age = (target - source).days
    stale = age < 0 or age > limit
    if age < 0:
        message = f"{label} is dated after requested as-of"
    elif age > limit:
        message = f"{label} is {age} calendar days old"
    else:
        message = f"{label} freshness is within {limit} calendar days"
    return FreshnessCheck(source_as_of, age, limit, stale, message).as_dict()


def _next_month_end(value: str | None) -> str | None:
    if not value:
        return None
    current = date.fromisoformat(value)
    year = current.year + (1 if current.month == 12 else 0)
    month = 1 if current.month == 12 else current.month + 1
    return date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def _temporal_errors(
    *,
    market_data_as_of: str,
    decision_date: str,
    governance_state_as_of: str | None,
    snapshot_mode: str,
    research_source_as_of: str | None,
    execution_source_as_of: str | None,
) -> list[str]:
    cutoff = date.fromisoformat(market_data_as_of)
    decision = date.fromisoformat(decision_date)
    errors = []
    for label, value in (
        ("research report", research_source_as_of),
        ("execution validation report", execution_source_as_of),
    ):
        if value and date.fromisoformat(value) > cutoff:
            errors.append(f"{label} is dated after market data cutoff")
    if governance_state_as_of:
        governance = date.fromisoformat(governance_state_as_of)
        if governance > decision:
            errors.append("governance state is dated after decision date")
        if snapshot_mode == "historical_snapshot" and governance > cutoff:
            errors.append("historical snapshot governance state is dated after as-of")
    return errors
