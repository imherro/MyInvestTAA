import hashlib
import json

from engine.asset_registry.loader import ASSET_MAPPING_FILE, ROOT


PROPOSAL = ROOT / "reports" / "execution_mapping_proposal.json"
COUNTER = ROOT / "reports" / "execution_mapping_counterfactual_report.json"
COUNTERFACTUAL_BASELINE_SOURCES = {
    "asset_mapping": ASSET_MAPPING_FILE,
    "decision_ledger": ROOT / "data" / "universe" / "execution_mapping_decision_ledger.json",
    "approval_integrity_seal": ROOT / "reports" / "execution_mapping_approval_integrity_seal.json",
    "execution_backtest_report": ROOT / "reports" / "execution_backtest_report.json",
}
COUNTERFACTUAL_INPUT_SOURCES = {
    "execution_mapping_proposal": PROPOSAL,
    "research_backtest_report": ROOT / "reports" / "research_backtest_report.json",
    "execution_price_dataset_manifest": ROOT / "reports" / "execution_price_dataset_manifest.json",
    **COUNTERFACTUAL_BASELINE_SOURCES,
    "execution_engine_code": ROOT / "backtest" / "execution" / "engine.py",
    "counterfactual_code": ROOT / "backtest" / "execution" / "counterfactual.py",
    "proposal_report_code": ROOT / "backtest" / "execution" / "proposal_report.py",
}
JSON_SOURCE_NAMES = {
    "execution_mapping_proposal",
    "research_backtest_report",
    "execution_price_dataset_manifest",
    "asset_mapping",
    "decision_ledger",
    "approval_integrity_seal",
    "execution_backtest_report",
}


def write_report(report, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_report(path, message):
    if not path.exists():
        return {"available": False, "status": "unavailable", "message": message}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {"available": False, "status": "unavailable", "message": f"{message}: {type(exc).__name__}"}
    if not isinstance(value, dict):
        return {"available": False, "status": "unavailable", "message": f"{message}: root must be an object"}
    value["available"] = True
    return value


def load_mapping_proposal_report():
    return load_report(PROPOSAL, "execution mapping proposal report not generated yet")


def build_counterfactual_baseline_contract():
    source_rows, errors = _build_source_rows(COUNTERFACTUAL_BASELINE_SOURCES)
    execution_report = _read_json_object(COUNTERFACTUAL_BASELINE_SOURCES["execution_backtest_report"])
    if execution_report is None:
        errors.append("baseline snapshot cannot be built from execution_backtest_report")
    baseline_snapshot = _baseline_snapshot(execution_report or {})
    contract = {
        "schema_version": "1.1",
        "sources": source_rows,
        "baseline_snapshot": baseline_snapshot,
        "baseline_snapshot_hash": _semantic_hash(baseline_snapshot),
        "valid": not errors,
        "errors": list(dict.fromkeys(errors)),
    }
    contract["contract_hash"] = _semantic_hash(contract)
    return contract


def build_counterfactual_input_contract():
    source_rows, errors = _build_source_rows(COUNTERFACTUAL_INPUT_SOURCES)
    proposal = _read_json_object(PROPOSAL)
    if proposal is None:
        errors.append("proposal overlay semantic hash cannot be built")
        overlay_hash = None
    else:
        overlay_hash = _semantic_hash(proposal.get("proposals", []))
    contract = {
        "schema_version": "1.0",
        "required_sources": source_rows,
        "proposal_overlay_semantic_hash": overlay_hash,
        "valid": not errors and _is_sha256(overlay_hash),
        "errors": list(dict.fromkeys(errors)),
    }
    contract["contract_hash"] = _semantic_hash(contract)
    return contract


def validate_counterfactual_baseline_contract(contract, baseline):
    expected = build_counterfactual_baseline_contract()
    errors = list(expected.get("errors", []))
    if not isinstance(contract, dict):
        errors.append("counterfactual baseline contract is missing")
    else:
        if contract.get("schema_version") != "1.1":
            errors.append("counterfactual baseline contract schema is unsupported")
        _compare_sources(contract.get("sources"), expected["sources"], errors, "baseline")
        if contract.get("baseline_snapshot") != expected["baseline_snapshot"]:
            errors.append("counterfactual baseline snapshot no longer matches current execution report")
        if contract.get("baseline_snapshot_hash") != expected["baseline_snapshot_hash"]:
            errors.append("counterfactual baseline snapshot hash mismatch")
        if _baseline_snapshot(baseline if isinstance(baseline, dict) else {}) != expected["baseline_snapshot"]:
            errors.append("counterfactual embedded baseline does not match current execution report")
        if contract.get("contract_hash") != expected["contract_hash"]:
            errors.append("counterfactual baseline contract hash mismatch")
        if not contract.get("valid"):
            errors.append("recorded counterfactual baseline contract is invalid")
    return _verification(errors, expected)


def validate_counterfactual_input_contract(contract):
    expected = build_counterfactual_input_contract()
    errors = list(expected.get("errors", []))
    if not isinstance(contract, dict):
        errors.append("counterfactual input contract is missing")
    else:
        if contract.get("schema_version") != "1.0":
            errors.append("counterfactual input contract schema is unsupported")
        _compare_sources(contract.get("required_sources"), expected["required_sources"], errors, "input")
        if contract.get("proposal_overlay_semantic_hash") != expected.get("proposal_overlay_semantic_hash"):
            errors.append("counterfactual proposal overlay semantic hash mismatch")
        if contract.get("contract_hash") != expected.get("contract_hash"):
            errors.append("counterfactual input contract hash mismatch")
        if not contract.get("valid"):
            errors.append("recorded counterfactual input contract is invalid")
    return _verification(errors, expected)


def validate_counterfactual_payload(value, *, expected_scope="mutable_pre_release", committed=False):
    if not isinstance(value, dict):
        return {"available": False, "status": "unavailable", "evidence_use": "unavailable", "message": "counterfactual payload is invalid"}
    value = dict(value)
    value["available"] = True
    baseline_status = validate_counterfactual_baseline_contract(value.get("baseline_contract"), value.get("baseline", {}))
    input_status = validate_counterfactual_input_contract(value.get("counterfactual_input_contract"))
    errors = [*baseline_status["errors"], *input_status["errors"]]
    if value.get("release_scope") != expected_scope:
        errors.append(f"counterfactual release scope mismatch: expected {expected_scope}")
    verified = not errors
    value["baseline_contract_verification"] = baseline_status
    value["input_contract_verification"] = input_status
    value["validation_errors"] = errors
    value["status"] = "current" if verified else "stale"
    value["evidence_use"] = "current_analysis" if verified else "historical_only"
    if not verified:
        if committed:
            return {"available": False, "status": "unavailable", "evidence_use": "unavailable", "message": "committed counterfactual validation failed", "errors": errors}
        decision = value.setdefault("decision", {})
        decision["ready_for_manual_mapping_approval"] = False
        decision["reasons"] = list(dict.fromkeys([*decision.get("reasons", []), "counterfactual inputs no longer match current formal sources"]))
        value.setdefault("warnings", []).append("Historical-only counterfactual: required inputs do not match the current formal sources.")
    return value


def load_counterfactual_report(path=None):
    target = path or COUNTER
    value = load_report(target, "execution mapping counterfactual report not generated or readable")
    if not value.get("available"):
        value.update({"available": False, "status": "unavailable", "evidence_use": "unavailable"})
        return value
    return validate_counterfactual_payload(value, expected_scope="mutable_pre_release")


def _build_source_rows(sources):
    rows = {}
    errors = []
    for name, path in sources.items():
        digest = _sha256(path)
        row = {"path": _display_path(path), "sha256": digest}
        if not _is_sha256(digest):
            errors.append(f"required source missing or SHA-256 invalid: {row['path']}")
        if name in JSON_SOURCE_NAMES and _read_json_value(path) is None:
            errors.append(f"required JSON source is missing or damaged: {row['path']}")
        rows[name] = row
    return rows, errors


def _compare_sources(recorded_sources, expected_sources, errors, label):
    recorded_sources = recorded_sources if isinstance(recorded_sources, dict) else {}
    for name, current in expected_sources.items():
        recorded = recorded_sources.get(name, {})
        if recorded.get("path") != current["path"]:
            errors.append(f"counterfactual {label} source path mismatch: {name}")
        recorded_hash = recorded.get("sha256")
        if not _is_sha256(recorded_hash):
            errors.append(f"counterfactual {label} source SHA-256 invalid: {name}")
        if recorded_hash != current["sha256"]:
            errors.append(f"counterfactual {label} source hash mismatch: {name}")


def _verification(errors, expected):
    errors = list(dict.fromkeys(errors))
    return {"verified": not errors, "status": "current" if not errors else "stale", "evidence_use": "current_analysis" if not errors else "historical_only", "errors": errors, "current_contract": expected}


def _read_json_object(path):
    value = _read_json_value(path)
    return value if isinstance(value, dict) else None


def _display_path(path):
    try:
        value = path.relative_to(ROOT)
    except ValueError:
        value = path
    return str(value).replace("\\", "/")


def _read_json_value(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return value


def _sha256(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _semantic_hash(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _baseline_snapshot(report):
    summary = report.get("mapping_summary", {}) if isinstance(report, dict) else {}
    return {
        "strategy": report.get("strategy") if isinstance(report, dict) else None,
        "data_provider": report.get("data_provider") if isinstance(report, dict) else None,
        "period": report.get("period") if isinstance(report, dict) else None,
        "metrics": report.get("metrics") if isinstance(report, dict) else None,
        "mapping_summary": {key: summary.get(key) for key in (
            "mapping_summary_schema_version", "executable_research_asset_count", "non_executable_research_asset_count",
            "no_approved_proxy_asset_count", "low_quality_excluded_asset_count", "executable_research_asset_ids",
            "non_executable_research_asset_ids", "no_approved_proxy_asset_ids", "low_quality_excluded_asset_ids",
            "untradable_months", "untradable_month_ratio", "binary_any_gap_month_ratio", "mapping_weight_coverage",
            "tradable_weight_coverage", "tradable_weight_coverage_total_portfolio", "coverage_contract", "gap_metrics",
            "mapping_count_scope",
        )},
        "aggregate_cash_breakdown": report.get("aggregate_cash_breakdown") if isinstance(report, dict) else None,
    }
