from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from current_taa.research_universe import ResearchAsset, ResearchUniverse
from data.models import PriceBar


AUDIT_MODES = {"offline", "provider_check"}
PROJECT_CONFIRMED_PROVIDER_CODES = {
    "H00300.CSI",
    "H00905.CSI",
    "H00852.CSI",
    "H00922.CSI",
    "480092.CNI",
}


class ResearchHistorySource(Protocol):
    def get_research_history(
        self, asset_id: str, start: str, end: str
    ) -> list[PriceBar]: ...


def audit_research_universe(
    universe: ResearchUniverse,
    *,
    root: Path,
    mode: str,
    source: ResearchHistorySource | None = None,
    generated_at: str | None = None,
) -> dict:
    if mode not in AUDIT_MODES:
        raise ValueError(f"unsupported audit mode: {mode}")
    if mode == "provider_check" and source is None:
        raise ValueError("provider_check mode requires a research history source")

    rows = [
        _audit_asset(asset, root=Path(root), mode=mode, source=source)
        for asset in universe.assets_for_tier("A")
    ]
    ready = sum(row["research_ready"] for row in rows)
    blocked = sum(not row["research_ready"] for row in rows)
    unverified = sum(
        universe.require_allowed_asset(row["asset_key"]).verification_status
        != "verified"
        for row in rows
    )
    return {
        "schema_version": "1.0",
        "report_type": "research_universe_audit",
        "universe_id": universe.universe_id,
        "universe_hash": universe.universe_hash,
        "mode": mode,
        "generated_at": generated_at or datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "total_whitelist_assets": len(universe.assets),
            "tier_a_count": len(universe.assets_for_tier("A")),
            "tier_b_count": len(universe.assets_for_tier("B")),
            "tier_c_count": len(universe.assets_for_tier("C")),
            "tier_a_ready": ready,
            "tier_a_blocked": blocked,
            "tier_a_unverified": unverified,
        },
        "assets": rows,
        "limitations": [
            "Provider availability does not independently prove total-return methodology.",
            "P0 audits price availability only; valuation and structural-validity filters are not implemented.",
            "B-tier and C-tier assets are contract-validated but are not queried in P0.",
        ],
    }


def write_audit_report(path: Path, report: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _audit_asset(
    asset: ResearchAsset,
    *,
    root: Path,
    mode: str,
    source: ResearchHistorySource | None,
) -> dict:
    local = _audit_local_cache(asset, root)
    provider = _not_checked_provider()
    if mode == "provider_check":
        provider = _audit_provider(asset, source)

    selected = (
        local
        if mode == "offline" or local["status"] == "available"
        else provider
    )
    basis_status, basis_evidence = _return_basis_evidence(asset, local)
    local_is_required = mode == "offline" or provider["status"] != "available"
    blockers = list(local["blockers"]) if local_is_required else []
    warnings = list(local["warnings"])
    if not local_is_required and local["status"] != "available":
        warnings.append(
            "Local cache is unavailable; provider history was audited without writing cache."
        )
    if asset.provider_code is None:
        blockers.append("provider_code is not verified")
    if mode == "provider_check" and provider["status"] != "available":
        blockers.extend(provider["blockers"])
    if basis_status != "confirmed":
        blockers.append(f"total-return basis is {basis_status}")
    if asset.verification_status != "verified":
        blockers.append(f"provider mapping is {asset.verification_status}")
    blockers = list(dict.fromkeys(blockers))
    research_ready = (
        asset.provider_code is not None
        and asset.verification_status == "verified"
        and basis_status == "confirmed"
        and selected["status"] == "available"
        and selected["sorted_unique_dates"]
        and selected["invalid_price_count"] == 0
        and not blockers
    )
    return {
        "asset_key": asset.asset_key,
        "display_name": asset.display_name,
        "tier": asset.tier,
        "official_code": asset.official_code,
        "provider_code": asset.provider_code,
        "contract_status": "valid",
        "provider_status": provider["status"],
        "local_cache_status": local["status"],
        "return_basis_status": basis_status,
        "first_date": selected["first_date"],
        "last_date": selected["last_date"],
        "row_count": selected["row_count"],
        "duplicate_dates": selected["duplicate_dates"],
        "invalid_price_count": selected["invalid_price_count"],
        "sorted_unique_dates": selected["sorted_unique_dates"],
        "research_ready": research_ready,
        "blockers": blockers,
        "warnings": warnings,
        "provider_evidence": provider["evidence"],
        "return_basis_evidence": basis_evidence,
        "verification_notes": [
            "Provider query success and total-return basis confirmation are separate conclusions.",
            "Valuation filter is not implemented in P0.",
            "Structural validity is unassessed in P0.",
        ],
    }


def _audit_local_cache(asset: ResearchAsset, root: Path) -> dict:
    if asset.provider_code is None:
        return _history_result("missing", blockers=["local cache has no provider mapping"])
    path = root / "data" / "research_prices" / _cache_file_name(asset.provider_code)
    if not path.exists():
        return _history_result("missing", blockers=["local research cache is missing"])
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _history_result("invalid", blockers=["local research cache is unreadable"])
    if not isinstance(values, list):
        return _history_result("invalid", blockers=["local research cache must be a list"])

    dates: list[str] = []
    invalid_price_count = 0
    invalid_basis = False
    malformed = False
    for value in values:
        try:
            date = str(value["date"])
            close = float(value["close"])
            basis = value["return_basis"]
        except (KeyError, TypeError, ValueError):
            malformed = True
            continue
        dates.append(date)
        if not math.isfinite(close) or close <= 0:
            invalid_price_count += 1
        if basis != "total_return":
            invalid_basis = True
    duplicates = sorted(date for date, count in Counter(dates).items() if count > 1)
    sorted_unique = bool(dates) and dates == sorted(set(dates))
    blockers = []
    if malformed:
        blockers.append("local research cache contains malformed rows")
    if invalid_price_count:
        blockers.append("local research cache contains non-positive or non-finite prices")
    if invalid_basis:
        blockers.append("local research cache return_basis is not total_return")
    if duplicates:
        blockers.append("local research cache contains duplicate dates")
    if dates and not sorted_unique and not duplicates:
        blockers.append("local research cache dates are not sorted")
    if not dates:
        blockers.append("local research cache contains no valid rows")
    status = "available" if not blockers else "invalid"
    return _history_result(
        status,
        dates=dates,
        duplicate_dates=duplicates,
        invalid_price_count=invalid_price_count,
        sorted_unique_dates=sorted_unique,
        blockers=blockers,
        basis_is_total_return=not invalid_basis and bool(dates),
    )


def _audit_provider(
    asset: ResearchAsset, source: ResearchHistorySource | None
) -> dict:
    if asset.provider_code is None:
        return _history_result(
            "unavailable", blockers=["provider_code is not verified"]
        )
    assert source is not None
    try:
        bars = source.get_research_history(
            asset.provider_code, "1990-01-01", datetime.now(UTC).date().isoformat()
        )
    except Exception as exc:
        return _history_result(
            "unavailable",
            blockers=[f"provider query failed: {type(exc).__name__}"],
        )
    result = _audit_provider_bars(asset.provider_code, bars)
    if result["status"] == "available":
        result["evidence"] = [
            "Tushare query returned non-empty valid history for the configured provider_code."
        ]
    return result


def _audit_provider_bars(provider_code: str, bars: Sequence[PriceBar]) -> dict:
    dates: list[str] = []
    invalid_price_count = 0
    wrong_asset = False
    for bar in bars:
        dates.append(str(bar.date))
        try:
            close = float(bar.close)
        except (TypeError, ValueError):
            invalid_price_count += 1
            continue
        if not math.isfinite(close) or close <= 0:
            invalid_price_count += 1
        if bar.asset_id != provider_code:
            wrong_asset = True
    duplicates = sorted(date for date, count in Counter(dates).items() if count > 1)
    sorted_unique = bool(dates) and dates == sorted(set(dates))
    blockers = []
    if not dates:
        blockers.append("provider returned empty history")
    if wrong_asset:
        blockers.append("provider returned a different asset_id")
    if invalid_price_count:
        blockers.append("provider returned invalid prices")
    if duplicates:
        blockers.append("provider returned duplicate dates")
    if dates and not sorted_unique and not duplicates:
        blockers.append("provider dates are not sorted")
    status = "available" if not blockers else "unavailable"
    return _history_result(
        status,
        dates=dates,
        duplicate_dates=duplicates,
        invalid_price_count=invalid_price_count,
        sorted_unique_dates=sorted_unique,
        blockers=blockers,
    )


def _return_basis_evidence(asset: ResearchAsset, local: dict) -> tuple[str, list[str]]:
    evidence = ["Listed as a total-return index in the V1.0 human reference."]
    if local["basis_is_total_return"]:
        evidence.append("Existing local research cache declares return_basis=total_return.")
    if (
        asset.provider_code in PROJECT_CONFIRMED_PROVIDER_CODES
        and asset.verification_status == "verified"
        and local["status"] == "available"
        and local["basis_is_total_return"]
    ):
        evidence.append("Provider mapping is present in the existing verified project configuration.")
        return "confirmed", evidence
    if asset.official_code == "399606":
        return "reference_only", evidence
    return "unresolved", evidence


def _history_result(
    status: str,
    *,
    dates: Sequence[str] = (),
    duplicate_dates: Sequence[str] = (),
    invalid_price_count: int = 0,
    sorted_unique_dates: bool = False,
    blockers: Sequence[str] = (),
    warnings: Sequence[str] = (),
    basis_is_total_return: bool = False,
) -> dict:
    return {
        "status": status,
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
        "row_count": len(dates),
        "duplicate_dates": list(duplicate_dates),
        "invalid_price_count": invalid_price_count,
        "sorted_unique_dates": sorted_unique_dates,
        "blockers": list(blockers),
        "warnings": list(warnings),
        "basis_is_total_return": basis_is_total_return,
        "evidence": [],
    }


def _not_checked_provider() -> dict:
    return _history_result("not_checked")


def _cache_file_name(provider_code: str) -> str:
    return provider_code.replace(".", "_") + ".json"
