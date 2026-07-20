from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_taa.drawdown_events import DrawdownAnalysis, analyze_drawdown_history
from current_taa.research_universe import ResearchAsset, load_research_universe


AUDIT_RELATIVE_PATH = "reports/strategy_research/universe_audit.json"
OUTPUT_RELATIVE_PATH = "reports/strategy_research/drawdown_events"
METHODOLOGY_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"


class DrawdownBuildError(ValueError):
    pass


def build_drawdown_report_set(
    root: Path, *, generated_at: str | None = None
) -> dict[str, dict[str, Any]]:
    project_root = Path(root)
    universe = load_research_universe(
        project_root / "config" / "research_universe_v1.json"
    )
    tier_a = universe.assets_for_tier("A")
    audit_path = project_root / AUDIT_RELATIVE_PATH
    audit_bytes = audit_path.read_bytes()
    audit = _load_json_bytes(audit_bytes, "research universe audit")
    audit_rows = _validate_audit(universe, tier_a, audit)
    audit_hash = hashlib.sha256(audit_bytes).hexdigest()
    reports: dict[str, dict[str, Any]] = {}
    index_assets: list[dict[str, Any]] = []

    for asset in tier_a:
        audit_row = audit_rows[asset.asset_key]
        if _is_analyzable(audit_row):
            report = _build_analyzed_report(
                project_root, asset, universe, audit_hash
            )
        else:
            report = _build_blocked_report(asset, universe, audit_hash, audit_row)
        name = f"{asset.asset_key}.json"
        reports[name] = report
        summary = report["event_summary"]
        period = report["period"] or {}
        current_state = report["current_state"] or {}
        index_assets.append(
            {
                "asset_key": asset.asset_key,
                "display_name": asset.display_name,
                "provider_code": asset.provider_code,
                "risk_family": asset.risk_family,
                "analysis_status": report["analysis_status"],
                "report_path": f"{OUTPUT_RELATIVE_PATH}/{name}",
                "first_date": period.get("first_date"),
                "last_date": period.get("last_date"),
                "row_count": period.get("row_count", 0),
                "completed_event_count": summary["completed_event_count"],
                "open_event_count": summary["open_event_count"],
                "current_drawdown": current_state.get("drawdown"),
                "blockers": report["blockers"],
            }
        )

    reports["index.json"] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": "a_tier_drawdown_event_index",
        "methodology_version": METHODOLOGY_VERSION,
        "universe_id": universe.universe_id,
        "universe_hash": universe.universe_hash,
        "source_audit_path": AUDIT_RELATIVE_PATH,
        "source_audit_sha256": audit_hash,
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "tier_a_assets": len(tier_a),
            "analyzed_assets": sum(
                row["analysis_status"] == "analyzed" for row in index_assets
            ),
            "blocked_assets": sum(
                row["analysis_status"] == "blocked" for row in index_assets
            ),
            "completed_events": sum(
                row["completed_event_count"] for row in index_assets
            ),
            "open_events": sum(row["open_event_count"] for row in index_assets),
        },
        "assets": index_assets,
        "limitations": _limitations(),
    }
    _validate_report_set(reports, tier_a)
    return reports


def publish_drawdown_report_set(
    target: Path, reports: dict[str, dict[str, Any]]
) -> None:
    target = Path(target)
    expected_keys = {"index.json"} | {
        f"{row['asset_key']}.json" for row in reports.get("index.json", {}).get("assets", [])
    }
    if set(reports) != expected_keys or len(reports) != 8:
        raise DrawdownBuildError("report set must contain one index and seven assets")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="drawdown-stage-", dir=target.parent))
    try:
        for name, report in reports.items():
            (stage / name).write_text(
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
        _validate_staged_reports(stage, reports)
        _replace_directory(target, stage)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _build_analyzed_report(
    root: Path,
    asset: ResearchAsset,
    universe,
    audit_hash: str,
) -> dict[str, Any]:
    assert asset.provider_code is not None
    cache_relative = (
        f"data/research_prices/{asset.provider_code.replace('.', '_')}.json"
    )
    cache_path = root / cache_relative
    cache_bytes = cache_path.read_bytes()
    rows = _load_json_bytes(cache_bytes, f"price cache for {asset.asset_key}")
    analysis = analyze_drawdown_history(rows, asset_key=asset.asset_key)
    completed = sum(event.completed for event in analysis.events)
    opened = sum(not event.completed for event in analysis.events)
    return {
        **_report_identity(asset, universe, audit_hash),
        "analysis_status": "analyzed",
        "source_cache_path": cache_relative,
        "source_cache_sha256": hashlib.sha256(cache_bytes).hexdigest(),
        "period": {
            "first_date": analysis.first_date,
            "last_date": analysis.last_date,
            "row_count": analysis.row_count,
        },
        "methodology": _methodology(),
        "current_state": analysis.current_state,
        "event_summary": {
            "completed_event_count": completed,
            "open_event_count": opened,
            "total_event_count": len(analysis.events),
        },
        "events": [event.to_dict() for event in analysis.events],
        "drawdown_series": [point.to_dict() for point in analysis.drawdown_series],
        "blockers": [],
        "limitations": _limitations(),
    }


def _build_blocked_report(
    asset: ResearchAsset, universe, audit_hash: str, audit_row: dict[str, Any]
) -> dict[str, Any]:
    return {
        **_report_identity(asset, universe, audit_hash),
        "analysis_status": "blocked",
        "source_cache_path": None,
        "source_cache_sha256": None,
        "period": None,
        "methodology": _methodology(),
        "current_state": None,
        "event_summary": {
            "completed_event_count": 0,
            "open_event_count": 0,
            "total_event_count": 0,
        },
        "events": [],
        "drawdown_series": [],
        "blockers": list(audit_row["blockers"]),
        "limitations": _limitations(),
    }


def _report_identity(asset: ResearchAsset, universe, audit_hash: str) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": "asset_drawdown_events",
        "methodology_version": METHODOLOGY_VERSION,
        "asset": {
            "asset_key": asset.asset_key,
            "display_name": asset.display_name,
            "official_code": asset.official_code,
            "provider_code": asset.provider_code,
            "tier": asset.tier,
            "risk_family": asset.risk_family,
        },
        "universe_id": universe.universe_id,
        "universe_hash": universe.universe_hash,
        "source_audit_path": AUDIT_RELATIVE_PATH,
        "source_audit_sha256": audit_hash,
    }


def _validate_audit(universe, tier_a, audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if audit.get("universe_id") != universe.universe_id:
        raise DrawdownBuildError("audit universe_id does not match contract")
    if audit.get("universe_hash") != universe.universe_hash:
        raise DrawdownBuildError("audit universe_hash does not match contract")
    rows = audit.get("assets")
    if not isinstance(rows, list):
        raise DrawdownBuildError("audit assets must be a list")
    keys = [row.get("asset_key") for row in rows if isinstance(row, dict)]
    expected = [asset.asset_key for asset in tier_a]
    if len(keys) != len(set(keys)):
        raise DrawdownBuildError("audit contains duplicate asset_key")
    if keys != expected:
        raise DrawdownBuildError("audit must contain exactly tier A in research order")
    indexed = {row["asset_key"]: row for row in rows}
    for asset in tier_a:
        row = indexed[asset.asset_key]
        expected_values = {
            "provider_code": asset.provider_code,
            "contract_research_status": asset.research_status,
            "contract_verification_status": asset.verification_status,
        }
        if any(row.get(key) != value for key, value in expected_values.items()):
            raise DrawdownBuildError(
                f"audit contract fields do not match {asset.asset_key}"
            )
        if row.get("contract_status") != "valid":
            raise DrawdownBuildError(f"audit contract is invalid for {asset.asset_key}")
    return indexed


def _is_analyzable(row: dict[str, Any]) -> bool:
    return (
        row.get("contract_research_status") == "available"
        and row.get("contract_verification_status") == "verified"
        and row.get("research_ready") is True
        and row.get("return_basis_status") == "confirmed"
        and row.get("local_cache_status") == "available"
    )


def _validate_report_set(reports: dict[str, dict[str, Any]], tier_a) -> None:
    expected = {"index.json"} | {f"{asset.asset_key}.json" for asset in tier_a}
    if set(reports) != expected:
        raise DrawdownBuildError("generated report names do not match tier A contract")
    index = reports["index.json"]
    if [row["asset_key"] for row in index["assets"]] != [
        asset.asset_key for asset in tier_a
    ]:
        raise DrawdownBuildError("index asset order does not match tier A contract")
    if index["summary"]["analyzed_assets"] + index["summary"]["blocked_assets"] != 7:
        raise DrawdownBuildError("index summary does not cover seven assets")


def _validate_staged_reports(
    stage: Path, reports: dict[str, dict[str, Any]]
) -> None:
    files = {path.name for path in stage.iterdir() if path.is_file()}
    if files != set(reports):
        raise DrawdownBuildError("staged report file set is incomplete")
    loaded = {
        name: json.loads((stage / name).read_text(encoding="utf-8")) for name in files
    }
    index = loaded["index.json"]
    audit_hash = index["source_audit_sha256"]
    universe_hash = index["universe_hash"]
    for row in index["assets"]:
        report_name = Path(row["report_path"]).name
        report = loaded.get(report_name)
        if report is None or report["asset"]["asset_key"] != row["asset_key"]:
            raise DrawdownBuildError("index references an invalid asset report")
        if report["universe_hash"] != universe_hash:
            raise DrawdownBuildError("asset universe_hash differs from index")
        if report["source_audit_sha256"] != audit_hash:
            raise DrawdownBuildError("asset audit hash differs from index")
    expected_summary = {
        "tier_a_assets": len(index["assets"]),
        "analyzed_assets": sum(
            report["analysis_status"] == "analyzed"
            for name, report in loaded.items()
            if name != "index.json"
        ),
        "blocked_assets": sum(
            report["analysis_status"] == "blocked"
            for name, report in loaded.items()
            if name != "index.json"
        ),
        "completed_events": sum(
            report["event_summary"]["completed_event_count"]
            for name, report in loaded.items()
            if name != "index.json"
        ),
        "open_events": sum(
            report["event_summary"]["open_event_count"]
            for name, report in loaded.items()
            if name != "index.json"
        ),
    }
    if index["summary"] != expected_summary:
        raise DrawdownBuildError("index summary differs from asset reports")


def _replace_directory(target: Path, stage: Path) -> None:
    backup = target.with_name(target.name + ".previous")
    if backup.exists():
        shutil.rmtree(backup)
    if target.exists():
        target.replace(backup)
    try:
        stage.replace(target)
    except Exception:
        if backup.exists() and not target.exists():
            backup.replace(target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _load_json_bytes(value: bytes, description: str):
    try:
        return json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DrawdownBuildError(f"cannot read {description}") from exc


def _methodology() -> dict[str, Any]:
    return {
        "high_watermark": "expanding maximum using observations through each date",
        "drawdown": "close / high_watermark - 1",
        "event_start": "first observation strictly below the current high watermark",
        "recovery": "first observation at or above the event peak value",
        "trough_tie": "first observation at the minimum value",
        "peak_tie": "most recent equal high while no event is open",
        "point_in_time_interface": "analyze_drawdown_history(..., as_of_date=trading_date)",
    }


def _limitations() -> list[str]:
    return [
        "This report establishes price drawdown facts only.",
        "Historical drawdown percentiles are not calculated.",
        "Recovery probabilities and forward returns are not calculated.",
        "Strategy parameters and portfolio weights are not designed.",
        "Blocked assets are not analyzed or substituted.",
        "Completed-event outcomes are hindsight records; historical decisions must use the as-of interface.",
    ]


def main() -> int:
    reports = build_drawdown_report_set(ROOT)
    target = ROOT / OUTPUT_RELATIVE_PATH
    publish_drawdown_report_set(target, reports)
    summary = reports["index.json"]["summary"]
    print(
        f"A-tier drawdown reports: analyzed={summary['analyzed_assets']} "
        f"blocked={summary['blocked_assets']} output={target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
