from __future__ import annotations

import hashlib
from pathlib import Path

from engine.asset_registry.loader import ROOT


REQUIRED_SOURCE_DEFINITIONS = {
    "market_and_v11": {
        "path": "reports/strategy_diagnosis_report.json",
        "temporal_role": "market_data",
    },
    "research_allocation": {
        "path": "reports/research_backtest_report.json",
        "temporal_role": "market_data",
    },
    "execution_validation": {
        "path": "reports/execution_backtest_report.json",
        "temporal_role": "market_data",
    },
    "execution_shadow": {
        "path": "reports/execution_aware_shadow_portfolio.json",
        "temporal_role": "market_data",
    },
    "execution_price_manifest": {
        "path": "reports/execution_price_dataset_manifest.json",
        "temporal_role": "market_data",
    },
    "approval_integrity": {
        "path": "reports/execution_mapping_approval_integrity_seal.json",
        "temporal_role": "governance",
    },
    "decision_ledger": {
        "path": "data/universe/execution_mapping_decision_ledger.json",
        "temporal_role": "governance",
    },
    "asset_mapping": {
        "path": "data/universe/asset_mapping.json",
        "temporal_role": "governance",
    },
    "execution_gate_policy": {
        "path": "config/execution_validation_policy.json",
        "temporal_role": "policy",
    },
    "execution_instrument_aliases": {
        "path": "data/universe/execution_instrument_aliases.json",
        "temporal_role": "registry",
    },
}

OPTIONAL_SOURCE_DEFINITIONS = {
    "v11_current_allocation": {
        "path": "reports/v11_current_allocation.json",
        "temporal_role": "market_data",
    }
}

ALL_SOURCE_DEFINITIONS = {
    **{
        name: {**definition, "required": True}
        for name, definition in REQUIRED_SOURCE_DEFINITIONS.items()
    },
    **{
        name: {**definition, "required": False}
        for name, definition in OPTIONAL_SOURCE_DEFINITIONS.items()
    },
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_current_decision_source_entry(
    name: str,
    row: object,
    *,
    root: Path = ROOT,
    path_overrides: dict[str, Path] | None = None,
) -> list[str]:
    definition = ALL_SOURCE_DEFINITIONS.get(name)
    if definition is None:
        return [f"unknown current decision source: {name}"]
    if not isinstance(row, dict):
        return [f"source manifest entry must be an object: {name}"]

    errors: list[str] = []
    expected_required = definition["required"]
    expected_path = definition["path"]
    expected_role = definition["temporal_role"]
    if row.get("source") != name:
        errors.append(f"source identity mismatch: {name}")
    if row.get("required") is not expected_required:
        errors.append(f"source required flag mismatch: {name}")
    if row.get("path") != expected_path:
        errors.append(f"source path mismatch: {name}")
    if row.get("temporal_role") != expected_role:
        errors.append(f"source temporal role mismatch: {name}")

    source = (
        path_overrides.get(name)
        if path_overrides and name in path_overrides
        else root / expected_path
    ).resolve()
    try:
        source.relative_to(root.resolve())
    except ValueError:
        if not (path_overrides and name in path_overrides):
            errors.append(f"source path escapes project root: {name}")
            return errors

    exists = source.exists()
    if row.get("available") is not exists:
        errors.append(f"source availability mismatch: {name}")
    if not exists:
        if expected_required:
            errors.append(f"required source missing: {name}")
        elif row.get("sha256") is not None:
            errors.append(f"missing optional source must not have a hash: {name}")
        return errors

    expected_hash = row.get("sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        errors.append(f"source hash invalid: {name}")
        return errors
    if sha256_file(source) != expected_hash:
        errors.append(f"required source hash mismatch: {name}")
    return errors


def verify_current_decision_sources(
    manifest: object,
    *,
    root: Path = ROOT,
    path_overrides: dict[str, Path] | None = None,
) -> dict:
    if not isinstance(manifest, dict):
        return {
            "valid": False,
            "required_count": len(REQUIRED_SOURCE_DEFINITIONS),
            "available_required_count": 0,
            "verified_count": 0,
            "errors": ["source manifest must be an object"],
        }

    errors: list[str] = []
    expected_names = set(ALL_SOURCE_DEFINITIONS)
    actual_names = set(manifest)
    for name in sorted(expected_names - actual_names):
        errors.append(f"canonical source missing: {name}")
    for name in sorted(actual_names - expected_names):
        qualifier = "required " if isinstance(manifest[name], dict) and manifest[name].get("required") else ""
        errors.append(f"unknown {qualifier}source: {name}")

    verified_count = 0
    available_required_count = 0
    for name, definition in ALL_SOURCE_DEFINITIONS.items():
        row = manifest.get(name)
        row_errors = verify_current_decision_source_entry(
            name, row, root=root, path_overrides=path_overrides
        )
        errors.extend(row_errors)
        if definition["required"] and isinstance(row, dict) and row.get("available"):
            available_required_count += 1
        if definition["required"] and not row_errors:
            verified_count += 1

    return {
        "valid": not errors,
        "required_count": len(REQUIRED_SOURCE_DEFINITIONS),
        "available_required_count": available_required_count,
        "verified_count": verified_count,
        "errors": errors,
    }
