from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from engine.asset_registry.loader import ROOT, load_execution_universe
from engine.asset_registry.models import ExecutionAsset
from engine.asset_registry.routing import get_asset_history


EXECUTION_TUSHARE_DATA_AUDIT_REPORT = ROOT / "reports" / "execution_universe_data_audit_tushare.json"


def build_execution_data_availability_audit(
    provider,
    start: str | None = None,
    end: str | None = None,
    assets: list[ExecutionAsset] | None = None,
) -> dict:
    rows = [_audit_asset(provider, asset, start, end) for asset in (assets or load_execution_universe())]
    return {
        "provider": getattr(provider, "name", provider.__class__.__name__),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "start": start,
        "end": end,
        "checked_assets": len(rows),
        "available_assets": sum(row["available"] for row in rows),
        "unavailable_assets": sum(not row["available"] for row in rows),
        "rows": rows,
        "warnings": [warning for row in rows for warning in row["warnings"]],
        "errors": [],
    }


def write_execution_data_availability_audit(report: dict, path: Path | None = None) -> Path:
    target = path or EXECUTION_TUSHARE_DATA_AUDIT_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_execution_data_availability_report(path: Path | None = None) -> dict:
    target = path or EXECUTION_TUSHARE_DATA_AUDIT_REPORT
    if not target.exists():
        return {"available": False, "message": f"execution universe data audit report not found: {target.name}"}
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["available"] = True
    payload["report_path"] = str(target)
    return payload


def _audit_asset(provider, asset: ExecutionAsset, start: str | None, end: str | None) -> dict:
    warnings: list[str] = []
    try:
        bars = get_asset_history(provider, asset, start=start, end=end)
        if not bars:
            return _row(asset, False, error="no rows returned", warnings=["data_unavailable"])
        return_types = sorted({bar.return_type for bar in bars})
        if return_types != [asset.return_basis]:
            warnings.append(
                "provider_return_type differs from registry return_basis: "
                f"{','.join(return_types)} vs {asset.return_basis}"
            )
        dates = sorted(bar.date for bar in bars)
        return _row(asset, True, len(bars), dates[0], dates[-1], None, warnings, return_types)
    except Exception as exc:  # Audit every ETF even if a single source request fails.
        return _row(asset, False, error=str(exc), warnings=["data_unavailable"])


def _row(
    asset: ExecutionAsset,
    available: bool,
    row_count: int = 0,
    first_date: str | None = None,
    last_date: str | None = None,
    error: str | None = None,
    warnings: list[str] | None = None,
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
        "warnings": warnings or [],
    }
