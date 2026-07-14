from __future__ import annotations

import json
from pathlib import Path
import shutil
from uuid import uuid4

from backtest.execution.v2.report import _hash_json, _promote, _read_json, _semantic_sha, _sha
from backtest.execution.v2.scenario import expected_run_id
from engine.asset_registry.loader import ROOT


REPORT = ROOT / "reports" / "execution_backtest_v2_b2_cost_report.json"
LEDGER = ROOT / "reports" / "execution_v2_b2_cost_ledger.json"
COMPARISON = ROOT / "reports" / "execution_v2_b1_b2_cost_comparison.json"
MANIFEST = ROOT / "reports" / "execution_v2_b2_cost_output_manifest.json"
COMMITTED = ROOT / "reports" / "execution_v2_b2_cost_COMMITTED.json"
ARTIFACTS = (REPORT, LEDGER, COMPARISON)


def write_cost_outputs(report, ledger, comparison):
    staging = ROOT / "reports" / ".execution-v2-b2-cost-staging" / uuid4().hex
    staging.mkdir(parents=True)
    try:
        values = {REPORT.name: report, LEDGER.name: ledger, COMPARISON.name: comparison}
        for name, value in values.items():
            (staging / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staged = {name: _read_json(staging / name) for name in values}
        cross_validate_cost_outputs(staged)
        artifacts = {name: {"sha256": _sha(staging / name), "semantic_sha256": _semantic_sha(staging / name)} for name in values}
        manifest = {
            "schema_version": "1.0", "run_id": report["run_id"], "scenario_id": report["scenario_id"],
            "policy_sha256": report["policy_sha256"], "b1_output_set_hash": report["b1_output_set_hash"],
            "date_grid_hash": comparison["date_grid_hash"], "artifacts": artifacts,
            "output_set_hash": _hash_json(artifacts), "verified": True, "errors": [],
        }
        manifest_path = staging / MANIFEST.name
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        marker = {"schema_version": "1.0", "run_id": report["run_id"], "output_set_hash": manifest["output_set_hash"], "manifest_sha256": _sha(manifest_path), "committed": True}
        (staging / COMMITTED.name).write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _promote(staging, (*ARTIFACTS, MANIFEST, COMMITTED))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def load_cost_report():
    result = verify_cost_output_set()
    if not result["verified"]:
        return {"available": False, "status": "unavailable", "message": "execution V2 B2 cost output integrity failed", "errors": result["errors"]}
    return result["report"]


def verify_cost_output_set():
    errors = []
    values = {}
    try:
        marker, manifest = _read_json(COMMITTED), _read_json(MANIFEST)
        if marker.get("committed") is not True or marker.get("manifest_sha256") != _sha(MANIFEST): errors.append("cost committed marker or manifest hash invalid")
        if marker.get("output_set_hash") != manifest.get("output_set_hash"): errors.append("cost output set hash mismatch")
        for path in ARTIFACTS:
            expected = manifest.get("artifacts", {}).get(path.name, {})
            if expected.get("sha256") != _sha(path) or expected.get("semantic_sha256") != _semantic_sha(path): errors.append(f"cost artifact hash mismatch: {path.name}")
            values[path.name] = _read_json(path)
        cross_validate_cost_outputs(values)
        report = values[REPORT.name]
        if expected_run_id(report) != report.get("run_id"): errors.append("cost run ID cannot be reproduced")
        for relative, details in report.get("source_manifest", {}).items():
            if relative == "cost_policy": continue
            if not (ROOT / relative).exists() or _sha(ROOT / relative) != details.get("sha256"): errors.append(f"cost source hash mismatch: {relative}")
        if report.get("production_actionable") is not False or report.get("eligible_to_replace_v1") is not False: errors.append("cost scenario production boundary invalid")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {"verified": not errors, "errors": errors, "report": values.get(REPORT.name, {})}


def cross_validate_cost_outputs(values):
    report, ledger, comparison = values[REPORT.name], values[LEDGER.name], values[COMPARISON.name]
    if len({report.get("run_id"), ledger.get("run_id"), comparison.get("run_id")}) != 1: raise ValueError("cost artifact run IDs disagree")
    if len({report.get("policy_sha256"), ledger.get("policy_sha256"), comparison.get("policy_sha256")}) != 1: raise ValueError("cost artifact policies disagree")
    if report.get("b1_output_set_hash") != comparison.get("b1_output_set_hash"): raise ValueError("B1 baseline output set hash disagrees")
    ledger_total = round(sum(row["total_cost"] for row in ledger.get("rows", [])), 10)
    daily_total = round(sum(row["transaction_cost"] for row in report.get("daily_portfolio_states", [])), 10)
    if ledger_total != ledger.get("summary", {}).get("total_cost") or ledger_total != report.get("cost_attribution", {}).get("total_cost") or ledger_total != daily_total: raise ValueError("cost totals do not reconcile")
    dates = [row["date"] for row in report.get("net_cost_curve", [])]
    if dates != [row["date"] for row in report.get("gross_zero_cost_curve", [])] or _hash_json(dates) != comparison.get("date_grid_hash"): raise ValueError("cost scenario date grids disagree")
    if any(row.get("policy_sha256") != report.get("policy_sha256") for row in ledger.get("rows", [])): raise ValueError("cost ledger policy hash disagrees")
