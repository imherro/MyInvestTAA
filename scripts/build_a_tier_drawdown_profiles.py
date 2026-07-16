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

from current_taa.drawdown_profiles import build_drawdown_profile
from current_taa.research_universe import ResearchAsset, load_research_universe


EVENT_INDEX_RELATIVE = "reports/strategy_research/drawdown_events/index.json"
AUDIT_RELATIVE = "reports/strategy_research/universe_audit.json"
OUTPUT_RELATIVE = "reports/strategy_research/drawdown_profiles"


class DrawdownProfileBuildError(ValueError):
    pass


def build_drawdown_profile_report_set(
    root: Path, *, generated_at: str | None = None
) -> dict[str, dict[str, Any]]:
    root = Path(root)
    universe = load_research_universe(root / "config/research_universe_v1.json")
    tier_a = universe.assets_for_tier("A")
    audit_bytes = (root / AUDIT_RELATIVE).read_bytes()
    event_index_bytes = (root / EVENT_INDEX_RELATIVE).read_bytes()
    audit = _load_json(audit_bytes, "universe audit")
    event_index = _load_json(event_index_bytes, "drawdown event index")
    _validate_source_index(universe, tier_a, audit_bytes, audit, event_index)
    _validate_event_file_set(root, tier_a)
    source_index_hash = hashlib.sha256(event_index_bytes).hexdigest()
    reports: dict[str, dict[str, Any]] = {}
    index_assets: list[dict[str, Any]] = []
    source_rows = {row["asset_key"]: row for row in event_index["assets"]}
    source_totals = {"analyzed": 0, "blocked": 0, "completed": 0, "open": 0}

    for asset in tier_a:
        source_row = source_rows[asset.asset_key]
        expected_relative = (
            f"reports/strategy_research/drawdown_events/{asset.asset_key}.json"
        )
        if source_row.get("report_path") != expected_relative:
            raise DrawdownProfileBuildError("event report path is not canonical")
        event_bytes = (root / expected_relative).read_bytes()
        event_report = _load_json(event_bytes, f"event report {asset.asset_key}")
        event_hash = hashlib.sha256(event_bytes).hexdigest()
        _validate_event_identity(
            asset, source_row, event_report, universe.universe_hash, event_index
        )
        source_totals[event_report["analysis_status"]] += 1
        source_totals["completed"] += event_report["event_summary"][
            "completed_event_count"
        ]
        source_totals["open"] += event_report["event_summary"]["open_event_count"]
        profile_body = build_drawdown_profile(event_report)
        report = {
            "schema_version": "1.0",
            "report_type": "asset_drawdown_profile",
            "methodology_version": "1.0",
            "analysis_status": event_report["analysis_status"],
            "asset": event_report["asset"],
            "universe_id": universe.universe_id,
            "universe_hash": universe.universe_hash,
            "source_event_index_path": EVENT_INDEX_RELATIVE,
            "source_event_index_sha256": source_index_hash,
            "source_event_report_path": expected_relative,
            "source_event_report_sha256": event_hash,
            "period": profile_body.get("period"),
            "daily_depth_profile": profile_body["daily_depth_profile"],
            "event_depth_profile": profile_body["event_depth_profile"],
            "duration_profile": profile_body["duration_profile"],
            "current_position": profile_body["current_position"],
            "blockers": list(event_report.get("blockers", [])),
            "limitations": _limitations(),
        }
        name = f"{asset.asset_key}.json"
        reports[name] = report
        current = report["current_position"] or {}
        index_assets.append(
            {
                "asset_key": asset.asset_key,
                "display_name": asset.display_name,
                "risk_family": asset.risk_family,
                "analysis_status": report["analysis_status"],
                "report_path": f"{OUTPUT_RELATIVE}/{name}",
                "current_drawdown": current.get("current_drawdown"),
                "current_depth": current.get("current_depth"),
                "current_all_observations_percentile": current.get(
                    "all_observations_percentile"
                ),
                "completed_event_count": event_report["event_summary"][
                    "completed_event_count"
                ],
                "open_event_count": event_report["event_summary"]["open_event_count"],
                "source_event_report_sha256": event_hash,
                "blockers": report["blockers"],
            }
        )

    expected_source = {
        "analyzed": event_index["summary"]["analyzed_assets"],
        "blocked": event_index["summary"]["blocked_assets"],
        "completed": event_index["summary"]["completed_events"],
        "open": event_index["summary"]["open_events"],
    }
    if source_totals != expected_source:
        raise DrawdownProfileBuildError(
            "event index summary differs from asset reports"
        )
    reports["index.json"] = {
        "schema_version": "1.0",
        "report_type": "a_tier_drawdown_profile_index",
        "methodology_version": "1.0",
        "universe_id": universe.universe_id,
        "universe_hash": universe.universe_hash,
        "source_event_index_path": EVENT_INDEX_RELATIVE,
        "source_event_index_sha256": source_index_hash,
        "generated_at": generated_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "tier_a_assets": len(tier_a),
            "analyzed_assets": source_totals["analyzed"],
            "blocked_assets": source_totals["blocked"],
        },
        "assets": index_assets,
        "limitations": _limitations(),
    }
    _validate_report_names(reports, tier_a)
    return reports


def publish_drawdown_profile_report_set(
    target: Path, reports: dict[str, dict[str, Any]]
) -> None:
    target = Path(target)
    if len(reports) != 8 or "index.json" not in reports:
        raise DrawdownProfileBuildError("profile report set must contain eight files")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="profile-stage-", dir=target.parent))
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
        _validate_stage(stage, reports)
        _replace_directory(target, stage)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _validate_source_index(universe, tier_a, audit_bytes, audit, event_index) -> None:
    if event_index.get("universe_id") != universe.universe_id or event_index.get(
        "universe_hash"
    ) != universe.universe_hash:
        raise DrawdownProfileBuildError("event index does not match universe")
    if audit.get("universe_id") != universe.universe_id or audit.get(
        "universe_hash"
    ) != universe.universe_hash:
        raise DrawdownProfileBuildError("audit does not match universe")
    if event_index.get("source_audit_sha256") != hashlib.sha256(
        audit_bytes
    ).hexdigest():
        raise DrawdownProfileBuildError("event index audit hash is stale")
    rows = event_index.get("assets")
    expected = [asset.asset_key for asset in tier_a]
    if not isinstance(rows, list) or [row.get("asset_key") for row in rows] != expected:
        raise DrawdownProfileBuildError("event index must contain tier A in order")
    if event_index.get("summary", {}).get("tier_a_assets") != 7:
        raise DrawdownProfileBuildError("event index summary does not cover tier A")
    for asset, row in zip(tier_a, rows, strict=True):
        if not isinstance(row, dict):
            raise DrawdownProfileBuildError("event index asset row must be an object")
        if row.get("provider_code") != asset.provider_code or row.get(
            "risk_family"
        ) != asset.risk_family:
            raise DrawdownProfileBuildError(
                "event index identity differs from universe"
            )


def _validate_event_identity(
    asset: ResearchAsset,
    source_row: dict,
    report: dict,
    universe_hash: str,
    event_index: dict,
) -> None:
    identity = report.get("asset", {})
    expected = {
        "asset_key": asset.asset_key,
        "provider_code": asset.provider_code,
        "risk_family": asset.risk_family,
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise DrawdownProfileBuildError("event report identity differs from index")
    if report.get("analysis_status") != source_row.get("analysis_status"):
        raise DrawdownProfileBuildError("event report status differs from index")
    if report.get("universe_id") != event_index.get("universe_id") or report.get(
        "universe_hash"
    ) != universe_hash or report.get(
        "source_audit_sha256"
    ) != event_index.get("source_audit_sha256"):
        raise DrawdownProfileBuildError("event report source chain differs from index")


def _validate_event_file_set(root: Path, tier_a: tuple[ResearchAsset, ...]) -> None:
    event_directory = root / Path(EVENT_INDEX_RELATIVE).parent
    expected = {"index.json"} | {
        f"{asset.asset_key}.json" for asset in tier_a
    }
    try:
        actual = {
            path.name
            for path in event_directory.iterdir()
            if path.is_file() and path.suffix.lower() == ".json"
        }
    except OSError as exc:
        raise DrawdownProfileBuildError(
            "cannot inspect event source directory"
        ) from exc
    if actual != expected:
        raise DrawdownProfileBuildError(
            "event source directory must contain exactly the approved eight JSON files"
        )


def _validate_report_names(reports, tier_a) -> None:
    expected = {"index.json"} | {f"{asset.asset_key}.json" for asset in tier_a}
    if set(reports) != expected:
        raise DrawdownProfileBuildError("profile report names differ from tier A")


def _validate_stage(stage: Path, reports: dict[str, dict[str, Any]]) -> None:
    if {path.name for path in stage.iterdir() if path.is_file()} != set(reports):
        raise DrawdownProfileBuildError("staged profile reports are incomplete")
    loaded = {
        name: json.loads((stage / name).read_text(encoding="utf-8"))
        for name in reports
    }
    index = loaded["index.json"]
    analyzed = blocked = 0
    for row in index["assets"]:
        name = Path(row["report_path"]).name
        report = loaded.get(name)
        if report is None or report["asset"]["asset_key"] != row["asset_key"]:
            raise DrawdownProfileBuildError("profile index reference is invalid")
        if report["universe_hash"] != index["universe_hash"]:
            raise DrawdownProfileBuildError("profile universe hashes differ")
        if report["source_event_index_sha256"] != index[
            "source_event_index_sha256"
        ]:
            raise DrawdownProfileBuildError("profile event index hashes differ")
        if report["source_event_report_sha256"] != row[
            "source_event_report_sha256"
        ]:
            raise DrawdownProfileBuildError("profile event report hash differs")
        analyzed += report["analysis_status"] == "analyzed"
        blocked += report["analysis_status"] == "blocked"
    if index["summary"] != {
        "tier_a_assets": 7,
        "analyzed_assets": analyzed,
        "blocked_assets": blocked,
    }:
        raise DrawdownProfileBuildError("profile index summary differs from reports")


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


def _load_json(value: bytes, description: str) -> dict[str, Any]:
    try:
        result = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DrawdownProfileBuildError(f"cannot read {description}") from exc
    if not isinstance(result, dict):
        raise DrawdownProfileBuildError(f"{description} must be an object")
    return result


def _limitations() -> list[str]:
    return [
        "Profiles are descriptive price-drawdown facts, not trading signals.",
        "Recovery probabilities, forward returns, and strategy parameters are "
        "not calculated.",
        "Open events are right-censored and excluded from completed duration "
        "distributions.",
        "Excluding open events does not remove censoring bias; later recovery "
        "research must address it explicitly.",
        "Blocked assets are not analyzed or substituted.",
    ]


def main() -> int:
    reports = build_drawdown_profile_report_set(ROOT)
    target = ROOT / OUTPUT_RELATIVE
    publish_drawdown_profile_report_set(target, reports)
    summary = reports["index.json"]["summary"]
    print(
        f"A-tier drawdown profiles: analyzed={summary['analyzed_assets']} "
        f"blocked={summary['blocked_assets']} output={target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
