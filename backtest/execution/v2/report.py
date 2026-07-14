from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from engine.asset_registry.loader import ROOT


REPORT = ROOT / "reports" / "execution_backtest_v2_report.json"
TIMELINE = ROOT / "reports" / "execution_investability_timeline.json"
COMPARISON = ROOT / "reports" / "execution_v1_v2_comparison.json"
MANIFEST = ROOT / "reports" / "execution_v2_output_manifest.json"
COMMITTED = ROOT / "reports" / "execution_v2_COMMITTED.json"
ARTIFACTS = (REPORT, TIMELINE, COMPARISON)


def write_execution_v2_outputs(report: dict, timeline: dict, comparison: dict) -> None:
    staging = ROOT / "reports" / ".execution-v2-staging" / uuid4().hex
    staging.mkdir(parents=True, exist_ok=False)
    try:
        values = {
            REPORT.name: report,
            TIMELINE.name: timeline,
            COMPARISON.name: comparison,
        }
        for name, value in values.items():
            indent = None if name == TIMELINE.name else 2
            (staging / name).write_text(
                json.dumps(value, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8"
            )
        _cross_validate(values)
        artifacts = {}
        for name in values:
            path = staging / name
            artifacts[name] = {
                "sha256": _sha(path),
                "semantic_sha256": _semantic_sha(path),
                "size_bytes": path.stat().st_size,
            }
        manifest = {
            "schema_version": "1.0",
            "strategy": report.get("strategy"),
            "generated_at": report.get("generated_at"),
            "input_source_manifest_hash": _hash_json(report.get("source_manifest", {})),
            "artifacts": artifacts,
            "output_set_hash": _hash_json(artifacts),
            "verified": True,
            "errors": [],
        }
        manifest_path = staging / MANIFEST.name
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        marker = {
            "schema_version": "1.0",
            "strategy": report.get("strategy"),
            "output_set_hash": manifest["output_set_hash"],
            "manifest_sha256": _sha(manifest_path),
            "committed": True,
        }
        (staging / COMMITTED.name).write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _promote(staging, (*ARTIFACTS, MANIFEST, COMMITTED))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def load_execution_v2_report(path: Path | None = None) -> dict:
    if path is not None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            value["available"] = True
            return value
        except (OSError, ValueError) as exc:
            return _unavailable([str(exc)])
    verified = verify_execution_v2_output_set()
    if not verified["verified"]:
        return _unavailable(verified["errors"])
    value = verified["report"]
    value["available"] = True
    return value


def verify_execution_v2_output_set() -> dict:
    errors = []
    values = {}
    try:
        marker = _read_json(COMMITTED)
        manifest = _read_json(MANIFEST)
        if marker.get("committed") is not True:
            errors.append("committed marker is not valid")
        if marker.get("manifest_sha256") != _sha(MANIFEST):
            errors.append("output manifest hash mismatch")
        if marker.get("output_set_hash") != manifest.get("output_set_hash"):
            errors.append("output set hash mismatch")
        for path in ARTIFACTS:
            expected = manifest.get("artifacts", {}).get(path.name, {})
            if expected.get("sha256") != _sha(path):
                errors.append(f"artifact raw hash mismatch: {path.name}")
            if expected.get("semantic_sha256") != _semantic_sha(path):
                errors.append(f"artifact semantic hash mismatch: {path.name}")
            values[path.name] = _read_json(path)
        if manifest.get("output_set_hash") != _hash_json(manifest.get("artifacts", {})):
            errors.append("manifest output_set_hash is invalid")
        _cross_validate(values)
        report = values[REPORT.name]
        if manifest.get("input_source_manifest_hash") != _hash_json(report.get("source_manifest", {})):
            errors.append("input source manifest hash mismatch")
        errors.extend(_verify_current_sources(report.get("source_manifest", {})))
        if report.get("strategy") != "EXECUTION_PROXY_V2_EXPERIMENTAL":
            errors.append("unexpected V2 strategy")
        if report.get("engine_status") != "experimental_validation_only":
            errors.append("unexpected V2 engine status")
        if report.get("production_actionable") is not False or report.get("eligible_to_replace_v1") is not False:
            errors.append("V2 production boundary is invalid")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {"verified": not errors, "errors": errors, "report": values.get(REPORT.name, {})}


def _cross_validate(values):
    report = values[REPORT.name]
    timeline = values[TIMELINE.name]
    comparison = values[COMPARISON.name]
    if report.get("comparison_to_v1") != comparison:
        raise ValueError("report and comparison artifact disagree")
    if report.get("strategy") != timeline.get("strategy"):
        raise ValueError("report and timeline strategy disagree")
    if report.get("periods", {}).get("master_calendar_period") != timeline.get("period"):
        raise ValueError("report and timeline periods disagree")
    counts = {}
    for row in timeline.get("rows", []):
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    summary = report.get("investability_summary", {})
    if counts != summary.get("state_counts") or len(timeline.get("rows", [])) != summary.get("timeline_row_count"):
        raise ValueError("timeline summary cannot be reproduced")


def _verify_current_sources(source_manifest):
    errors = []
    for relative, details in source_manifest.items():
        path = ROOT / relative
        if not path.exists() or details.get("sha256") != _sha(path):
            errors.append(f"current input hash mismatch: {relative}")
    return errors


def _promote(staging, targets):
    backup = staging / "backup"
    backup.mkdir()
    existing = set()
    try:
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.copy2(target, backup / target.name)
                existing.add(target.name)
        for target in targets:
            _replace_file(staging / target.name, target)
    except Exception:
        for target in targets:
            old = backup / target.name
            if target.name in existing:
                os.replace(old, target)
            elif target.exists():
                target.unlink()
        raise


def _replace_file(source, target):
    os.replace(source, target)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _semantic_sha(path):
    return _hash_json(_read_json(path))


def _hash_json(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unavailable(errors):
    return {
        "available": False,
        "status": "unavailable",
        "message": "execution V2 output integrity failed",
        "errors": list(errors),
    }
