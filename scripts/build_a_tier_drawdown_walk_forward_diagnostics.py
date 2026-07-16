from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_taa.drawdown_threshold_cohorts import THRESHOLD_FAMILIES
from current_taa.drawdown_walk_forward_diagnostics import (
    build_walk_forward_diagnostics,
)
from current_taa.research_universe import ResearchAsset, load_research_universe
from scripts.build_a_tier_drawdown_profiles import _load_json, _replace_directory
from scripts.build_a_tier_drawdown_walk_forward_evidence import (
    COHORT_INDEX_RELATIVE,
    EVENT_INDEX_RELATIVE,
    OUTCOME_INDEX_RELATIVE,
    STATISTICS_INDEX_RELATIVE,
    OUTPUT_RELATIVE as LEDGER_OUTPUT_RELATIVE,
    _validate_json_file_set,
    build_drawdown_walk_forward_evidence_report_set,
)


LEDGER_INDEX_RELATIVE = f"{LEDGER_OUTPUT_RELATIVE}/index.json"
OUTPUT_RELATIVE = "reports/strategy_research/drawdown_walk_forward_diagnostics"
SOURCE_INDEX_PATHS = {
    "event": EVENT_INDEX_RELATIVE,
    "outcome": OUTCOME_INDEX_RELATIVE,
    "cohort": COHORT_INDEX_RELATIVE,
    "statistics": STATISTICS_INDEX_RELATIVE,
    "ledger": LEDGER_INDEX_RELATIVE,
}
SOURCE_DIRECTORIES = {
    key: str(Path(path).parent) for key, path in SOURCE_INDEX_PATHS.items()
}


class DrawdownWalkForwardDiagnosticBuildError(ValueError):
    pass


def build_drawdown_walk_forward_diagnostic_report_set(
    root: Path, *, generated_at: str | None = None
) -> dict[str, dict[str, Any]]:
    root = Path(root)
    universe = load_research_universe(root / "config/research_universe_v1.json")
    tier_a = universe.assets_for_tier("A")
    for key, index_path in SOURCE_INDEX_PATHS.items():
        try:
            _validate_json_file_set(root, index_path, tier_a, key)
        except ValueError as exc:
            raise DrawdownWalkForwardDiagnosticBuildError(str(exc)) from exc

    source_index_bytes = {
        key: (root / path).read_bytes()
        for key, path in SOURCE_INDEX_PATHS.items()
    }
    source_indexes = {
        key: _load_json(payload, f"{key} index")
        for key, payload in source_index_bytes.items()
    }
    try:
        expected_ledgers = build_drawdown_walk_forward_evidence_report_set(
            root, generated_at=source_indexes["ledger"].get("generated_at")
        )
    except ValueError as exc:
        raise DrawdownWalkForwardDiagnosticBuildError(str(exc)) from exc
    formal_ledgers = _load_report_set(root, LEDGER_OUTPUT_RELATIVE, expected_ledgers)
    if formal_ledgers != expected_ledgers:
        raise DrawdownWalkForwardDiagnosticBuildError(
            "formal ledger business content differs from recomputation"
        )

    _validate_index_chain(source_indexes, source_index_bytes, universe.universe_id, universe.universe_hash)
    index_hashes = {
        key: hashlib.sha256(payload).hexdigest()
        for key, payload in source_index_bytes.items()
    }
    reports: dict[str, dict[str, Any]] = {}
    index_assets = []
    totals = {"analyzed": 0, "blocked": 0, "groups": 0, "events": 0}
    for asset in tier_a:
        name = f"{asset.asset_key}.json"
        source_paths = {
            key: f"{directory}/{name}"
            for key, directory in SOURCE_DIRECTORIES.items()
        }
        source_bytes = {
            key: (root / path).read_bytes() for key, path in source_paths.items()
        }
        source_reports = {
            key: _load_json(payload, f"{key} report {asset.asset_key}")
            for key, payload in source_bytes.items()
        }
        _validate_source_identity(asset, source_reports)
        if source_reports["ledger"] != formal_ledgers[name]:
            raise DrawdownWalkForwardDiagnosticBuildError(
                "formal ledger business content differs from recomputation"
            )
        try:
            body = build_walk_forward_diagnostics(source_reports["event"])
        except ValueError as exc:
            raise DrawdownWalkForwardDiagnosticBuildError(str(exc)) from exc
        _validate_diagnostic_body(body, source_reports["event"]["analysis_status"])

        status = source_reports["event"]["analysis_status"]
        totals[status] += 1
        totals["groups"] += body["summary"]["threshold_group_count"]
        totals["events"] += body["summary"]["event_evaluation_count"]
        report = {
            "schema_version": "1.0",
            "report_type": "asset_drawdown_walk_forward_diagnostics",
            "methodology_version": "1.0",
            "analysis_status": status,
            "asset": source_reports["event"]["asset"],
            "universe_id": universe.universe_id,
            "universe_hash": universe.universe_hash,
            **_source_fields(source_paths, source_bytes, index_hashes),
            "period": body["period"],
            "summary": body["summary"],
            "threshold_diagnostics": body["threshold_diagnostics"],
            "blockers": list(source_reports["event"].get("blockers", [])),
            "limitations": _limitations(),
        }
        reports[name] = report
        index_assets.append(
            {
                "asset_key": asset.asset_key,
                "display_name": asset.display_name,
                "risk_family": asset.risk_family,
                "analysis_status": status,
                "report_path": f"{OUTPUT_RELATIVE}/{name}",
                **body["summary"],
                **{
                    f"source_{key}_report_sha256": report[f"source_{key}_report_sha256"]
                    for key in SOURCE_INDEX_PATHS
                },
                "blockers": report["blockers"],
            }
        )

    reports["index.json"] = {
        "schema_version": "1.0",
        "report_type": "a_tier_drawdown_walk_forward_diagnostic_index",
        "methodology_version": "1.0",
        "universe_id": universe.universe_id,
        "universe_hash": universe.universe_hash,
        **{
            f"source_{key}_index_path": path
            for key, path in SOURCE_INDEX_PATHS.items()
        },
        **{
            f"source_{key}_index_sha256": value
            for key, value in index_hashes.items()
        },
        "generated_at": generated_at or datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "tier_a_assets": len(tier_a),
            "analyzed_assets": totals["analyzed"],
            "blocked_assets": totals["blocked"],
            "threshold_groups_per_analyzed_asset": 15,
            "total_threshold_groups": totals["groups"],
            "total_event_evaluations": totals["events"],
        },
        "assets": index_assets,
        "limitations": _limitations(),
    }
    expected_names = {"index.json"} | {f"{asset.asset_key}.json" for asset in tier_a}
    if set(reports) != expected_names:
        raise DrawdownWalkForwardDiagnosticBuildError(
            "diagnostic report set differs from tier A"
        )
    _validate_finite(reports)
    return reports


def publish_drawdown_walk_forward_diagnostic_report_set(
    target: Path, reports: dict[str, dict[str, Any]]
) -> None:
    target = Path(target)
    if len(reports) != 8 or "index.json" not in reports:
        raise DrawdownWalkForwardDiagnosticBuildError(
            "diagnostic report set must contain eight files"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="walk-forward-diagnostic-stage-", dir=target.parent))
    try:
        for name, report in reports.items():
            (stage / name).write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
        _validate_stage(stage, reports)
        _replace_directory(target, stage)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _load_report_set(root: Path, directory: str, expected: dict[str, Any]) -> dict[str, Any]:
    return {
        name: _load_json((root / directory / name).read_bytes(), f"formal report {name}")
        for name in expected
    }


def _validate_index_chain(indexes: dict[str, dict[str, Any]], index_bytes: dict[str, bytes], universe_id: str, universe_hash: str) -> None:
    for index in indexes.values():
        if index.get("universe_id") != universe_id or index.get("universe_hash") != universe_hash:
            raise DrawdownWalkForwardDiagnosticBuildError("source universe identity differs")
    for downstream in ("outcome", "cohort", "statistics", "ledger"):
        position = list(SOURCE_INDEX_PATHS).index(downstream)
        for upstream in list(SOURCE_INDEX_PATHS)[:position]:
            field = f"source_{upstream}_index_sha256"
            if field in indexes[downstream] and indexes[downstream][field] != hashlib.sha256(index_bytes[upstream]).hexdigest():
                raise DrawdownWalkForwardDiagnosticBuildError("source index SHA chain differs")


def _validate_source_identity(asset: ResearchAsset, reports: dict[str, dict[str, Any]]) -> None:
    expected = {
        "asset_key": asset.asset_key,
        "provider_code": asset.provider_code,
        "risk_family": asset.risk_family,
    }
    if any(any(report.get("asset", {}).get(key) != value for key, value in expected.items()) for report in reports.values()):
        raise DrawdownWalkForwardDiagnosticBuildError("source report identity differs from universe")
    statuses = {report.get("analysis_status") for report in reports.values()}
    if len(statuses) != 1:
        raise DrawdownWalkForwardDiagnosticBuildError("source analysis statuses differ")
    if statuses == {"blocked"} and any(
        (
            reports["event"].get("events") != [],
            reports["outcome"].get("records") != [],
            reports["cohort"].get("cohorts") != [],
            reports["statistics"].get("threshold_statistics") != [],
            reports["ledger"].get("event_evaluations") != [],
        )
    ):
        raise DrawdownWalkForwardDiagnosticBuildError("blocked source reports must contain empty facts")


def _source_fields(paths: dict[str, str], payloads: dict[str, bytes], index_hashes: dict[str, str]) -> dict[str, str]:
    result = {}
    for key, path in paths.items():
        result[f"source_{key}_index_path"] = SOURCE_INDEX_PATHS[key]
        result[f"source_{key}_index_sha256"] = index_hashes[key]
        result[f"source_{key}_report_path"] = path
        result[f"source_{key}_report_sha256"] = hashlib.sha256(payloads[key]).hexdigest()
    return result


def _validate_diagnostic_body(body: dict[str, Any], status: str) -> None:
    diagnostics = body.get("threshold_diagnostics")
    if not isinstance(diagnostics, list):
        raise DrawdownWalkForwardDiagnosticBuildError("threshold diagnostics must be a list")
    if status == "blocked":
        if body != {"period": None, "summary": _empty_summary(), "threshold_diagnostics": []}:
            raise DrawdownWalkForwardDiagnosticBuildError("blocked diagnostic must be empty")
        return
    expected = [(family, level) for family, levels in THRESHOLD_FAMILIES for level, _ in levels]
    actual = [(row["threshold_family"], row["threshold_level"]) for row in diagnostics]
    if actual != expected or len(diagnostics) != 15:
        raise DrawdownWalkForwardDiagnosticBuildError("diagnostic threshold order is invalid")
    event_counts = {row["status_support"]["event_evaluation_count"] for row in diagnostics}
    if len(event_counts) != 1:
        raise DrawdownWalkForwardDiagnosticBuildError("diagnostic event counts differ by threshold")
    for row in diagnostics:
        support = row["status_support"]
        if support["threshold_available_count"] != support["reached_count"] + support["not_reached_completed_count"] + support["not_reached_open_censored_count"]:
            raise DrawdownWalkForwardDiagnosticBuildError("diagnostic support identity is invalid")
        if len(row["training_metric_trajectories"]) != 16 or len(row["trigger_recovery_prequential_diagnostics"]) != 5 or len(row["peak_recovery_prequential_diagnostics"]) != 5 or len(row["forward_return_prequential_diagnostics"]) != 5:
            raise DrawdownWalkForwardDiagnosticBuildError("diagnostic metric set is incomplete")
    expected_summary = {
        "threshold_group_count": 15,
        "event_evaluation_count": next(iter(event_counts)),
        "total_reached_evaluations": sum(row["status_support"]["reached_count"] for row in diagnostics),
    }
    if body.get("summary") != expected_summary:
        raise DrawdownWalkForwardDiagnosticBuildError("diagnostic summary differs from groups")
    _validate_finite(body)


def _empty_summary() -> dict[str, int]:
    return {"threshold_group_count": 0, "event_evaluation_count": 0, "total_reached_evaluations": 0}


def _validate_stage(stage: Path, reports: dict[str, dict[str, Any]]) -> None:
    if {path.name for path in stage.iterdir() if path.is_file()} != set(reports):
        raise DrawdownWalkForwardDiagnosticBuildError("staged diagnostic reports are incomplete")
    loaded = {name: json.loads((stage / name).read_text(encoding="utf-8")) for name in reports}
    index = loaded["index.json"]
    totals = {"analyzed": 0, "blocked": 0, "groups": 0, "events": 0}
    for row in index["assets"]:
        report = loaded.get(Path(row["report_path"]).name)
        if report is None or report["asset"]["asset_key"] != row["asset_key"]:
            raise DrawdownWalkForwardDiagnosticBuildError("diagnostic index reference is invalid")
        _validate_diagnostic_body({"period": report["period"], "summary": report["summary"], "threshold_diagnostics": report["threshold_diagnostics"]}, report["analysis_status"])
        for source in SOURCE_INDEX_PATHS:
            if report[f"source_{source}_index_sha256"] != index[f"source_{source}_index_sha256"] or report[f"source_{source}_report_sha256"] != row[f"source_{source}_report_sha256"]:
                raise DrawdownWalkForwardDiagnosticBuildError("diagnostic source chain differs from index")
        if row["analysis_status"] != report["analysis_status"] or row["blockers"] != report["blockers"] or any(row.get(field) != report["summary"].get(field) for field in _empty_summary()):
            raise DrawdownWalkForwardDiagnosticBuildError("diagnostic index row differs from report")
        status = report["analysis_status"]
        totals[status] += 1
        totals["groups"] += report["summary"]["threshold_group_count"]
        totals["events"] += report["summary"]["event_evaluation_count"]
    expected = {
        "tier_a_assets": 7,
        "analyzed_assets": totals["analyzed"],
        "blocked_assets": totals["blocked"],
        "threshold_groups_per_analyzed_asset": 15,
        "total_threshold_groups": totals["groups"],
        "total_event_evaluations": totals["events"],
    }
    if index["summary"] != expected:
        raise DrawdownWalkForwardDiagnosticBuildError("diagnostic index summary differs from reports")
    _validate_finite(loaded)


def _validate_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise DrawdownWalkForwardDiagnosticBuildError("diagnostic output must contain only finite numbers")
    if isinstance(value, dict):
        for nested in value.values():
            _validate_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _validate_finite(nested)


def _limitations() -> list[str]:
    return [
        "This report diagnoses reliability; it does not rank thresholds.",
        "No pass, elimination, or minimum-sample threshold is predefined.",
        "The fifteen threshold evaluations within one event are highly dependent.",
        "Small-sample Brier scores and calibration gaps can be extremely unstable.",
        "Open not-reached events remain right-censored.",
        "Recovery diagnostics exclude samples censored before a horizon and therefore have complete-case bias; they are not IPCW estimates.",
        "Forward-return diagnostics use only complete test windows.",
        "Changing training statistics can reflect sample growth rather than structural failure.",
        "Assets are not pooled.",
        "No parameter selection, positions, trade instructions, or strategy returns are produced.",
    ]


def main() -> int:
    reports = build_drawdown_walk_forward_diagnostic_report_set(ROOT)
    publish_drawdown_walk_forward_diagnostic_report_set(ROOT / OUTPUT_RELATIVE, reports)
    summary = reports["index.json"]["summary"]
    print(f"A-tier walk-forward diagnostics: analyzed={summary['analyzed_assets']} blocked={summary['blocked_assets']} groups={summary['total_threshold_groups']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
