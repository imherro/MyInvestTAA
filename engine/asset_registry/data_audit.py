from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from data_provider.mock_provider import MockProvider
from engine.asset_registry.loader import ROOT, load_research_universe
from engine.asset_registry.models import ResearchAsset
from engine.asset_registry.routing import get_asset_history


RESEARCH_DATA_AUDIT_REPORT = ROOT / "reports" / "research_universe_data_audit.json"
RESEARCH_TUSHARE_DATA_AUDIT_REPORT = ROOT / "reports" / "research_universe_data_audit_tushare.json"


def build_research_data_availability_audit(
    provider,
    start: str | None = None,
    end: str | None = None,
    max_assets: int | None = None,
) -> dict:
    assets = load_research_universe()
    if max_assets is not None:
        assets = assets[:max_assets]

    rows = [
        _audit_asset(provider, asset, start=start, end=end)
        for asset in assets
    ]
    available_assets = sum(1 for row in rows if row["available"])
    unavailable_assets = len(rows) - available_assets
    warnings = [
        warning
        for row in rows
        for warning in row["warnings"]
    ]

    return {
        "provider": getattr(provider, "name", provider.__class__.__name__),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "start": start,
        "end": end,
        "checked_assets": len(rows),
        "available_assets": available_assets,
        "unavailable_assets": unavailable_assets,
        "rows": rows,
        "data_api_counts": _count_by(rows, "data_api"),
        "available_by_data_api": _available_by_data_api(rows),
        "warnings": warnings,
        "errors": [],
    }


def write_research_data_availability_audit(report: dict, path: Path | None = None) -> Path:
    target = path or RESEARCH_DATA_AUDIT_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_research_data_availability_report(path: Path | None = None, *, tushare: bool = False) -> dict:
    target = path or (RESEARCH_TUSHARE_DATA_AUDIT_REPORT if tushare else RESEARCH_DATA_AUDIT_REPORT)
    if not target.exists():
        return {
            "available": False,
            "message": f"research universe data audit report not found: {target.name}",
        }
    with target.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    payload["available"] = True
    payload["report_path"] = str(target)
    return payload


def build_research_universe_mock_provider() -> MockProvider:
    histories = {
        asset.asset_id: _mock_history_for_asset(asset, offset=index)
        for index, asset in enumerate(load_research_universe())
    }
    return MockProvider(assets=[], histories=histories, return_type="price")


def _audit_asset(provider, asset: ResearchAsset, start: str | None, end: str | None) -> dict:
    warnings = _asset_warnings(asset)
    try:
        bars = get_asset_history(provider, asset, start=start, end=end)
        if not bars:
            return _audit_row(asset, available=False, error="no rows returned", warnings=[*warnings, "data_unavailable"])
        provider_return_types = sorted({bar.return_type for bar in bars})
        warnings = [*warnings, *_return_type_warnings(asset, provider_return_types)]
        dates = sorted(bar.date for bar in bars)
        return _audit_row(
            asset,
            available=True,
            row_count=len(bars),
            first_date=dates[0],
            last_date=dates[-1],
            error=None,
            warnings=warnings,
            provider_return_types=provider_return_types,
        )
    except Exception as exc:  # noqa: BLE001 - audit must record per-asset failures.
        return _audit_row(
            asset,
            available=False,
            error=str(exc),
            warnings=[*warnings, "data_unavailable"],
        )


def _audit_row(
    asset: ResearchAsset,
    *,
    available: bool,
    row_count: int = 0,
    first_date: str | None = None,
    last_date: str | None = None,
    error: str | None,
    warnings: list[str],
    provider_return_types: list[str] | None = None,
) -> dict:
    return {
        "asset_id": asset.asset_id,
        "name": asset.name,
        "data_api": asset.data_api,
        "return_basis": asset.return_basis,
        "provider_return_types": provider_return_types or [],
        "available": available,
        "row_count": row_count,
        "first_date": first_date,
        "last_date": last_date,
        "error": error,
        "warnings": warnings,
    }


def _asset_warnings(asset: ResearchAsset) -> list[str]:
    warnings: list[str] = []
    if asset.return_basis == "price_index":
        warnings.append("price_index excludes dividend reinvestment")
    return warnings


def _return_type_warnings(asset: ResearchAsset, provider_return_types: list[str]) -> list[str]:
    if asset.return_basis != "total_return":
        return []
    if provider_return_types == ["total_return"]:
        return []
    return [
        "provider_return_type differs from registry return_basis: "
        f"{','.join(provider_return_types) or 'unknown'} vs {asset.return_basis}"
    ]


def _mock_history_for_asset(asset: ResearchAsset, *, offset: int) -> list[dict]:
    base = 100.0 + offset
    return [
        {
            "date": "2024-01-02",
            "close": base,
            "return_type": asset.return_basis,
        },
        {
            "date": "2024-06-28",
            "close": round(base * 1.05, 4),
            "return_type": asset.return_basis,
        },
        {
            "date": "2024-12-31",
            "close": round(base * 1.1, 4),
            "return_type": asset.return_basis,
        },
    ]


def _count_by(rows: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row[field])
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _available_by_data_api(rows: list[dict]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = counts.setdefault(str(row["data_api"]), {"available": 0, "unavailable": 0})
        key = "available" if row["available"] else "unavailable"
        bucket[key] += 1
    return dict(sorted(counts.items()))
