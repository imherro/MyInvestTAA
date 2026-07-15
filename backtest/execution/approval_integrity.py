from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from backtest.execution.approval_package import (
    APPROVAL_PACKAGE,
    DECISION_LEDGER,
    TARGET_ASSET_ID,
    TARGET_PROXY_ID,
)
from backtest.execution.approval_transaction import transaction_is_pending
from engine.asset_registry.loader import ASSET_MAPPING_FILE, ROOT


APPROVAL_RECORD = ROOT / "reports" / "execution_mapping_approval_record.json"
APPROVAL_INTEGRITY_SEAL = (
    ROOT / "reports" / "execution_mapping_approval_integrity_seal.json"
)
APPROVED_MAPPING_QUALITY = "medium"


def seal_existing_mapping_approval(
    *,
    expected_package_hash: str,
    expected_mapping_after_hash: str,
    decision_date: str,
    package_path: Path = APPROVAL_PACKAGE,
    record_path: Path = APPROVAL_RECORD,
    mapping_path: Path = ASSET_MAPPING_FILE,
    ledger_path: Path = DECISION_LEDGER,
    seal_path: Path = APPROVAL_INTEGRITY_SEAL,
) -> dict:
    if transaction_is_pending(_journal_for(mapping_path)):
        raise ValueError("approval transaction is pending")
    package_hash = _sha256_path(package_path)
    record_hash = _sha256_path(record_path)
    mapping_hash = _sha256_path(mapping_path)
    ledger_hash = _sha256_path(ledger_path)
    record = _load_json(record_path)
    mappings = _load_json(mapping_path)
    ledger = _load_json(ledger_path)
    target = _target_mapping(mappings)
    decision = _target_decision(ledger)
    approved_mappings = _approved_mappings(mappings, ledger)
    errors = _consistency_errors(
        expected_package_hash=expected_package_hash,
        actual_package_hash=package_hash,
        expected_mapping_hash=expected_mapping_after_hash,
        actual_mapping_hash=mapping_hash,
        decision_date=decision_date,
        record=record,
        target=target,
        decision=decision,
        record_name=record_path.name,
    )
    if errors:
        raise ValueError("; ".join(errors))
    seal = {
        "available": True,
        "verification_status": "verified",
        "approval_package_hash": package_hash,
        "approval_record_hash": record_hash,
        "current_mapping_hash": mapping_hash,
        "current_ledger_hash": ledger_hash,
        "target_mapping_row_hash": _hash_json(target),
        "approved_mapping_row_hashes": {
            row["research_asset_id"]: _hash_json(row)
            for row in approved_mappings
        },
        "approved_mappings": approved_mappings,
        "approved_asset": TARGET_ASSET_ID,
        "approved_proxy": TARGET_PROXY_ID,
        "approved_mapping_quality": APPROVED_MAPPING_QUALITY,
        "decision_date": decision_date,
        "production_approved": False,
        "errors": [],
    }
    _atomic_write_json(seal_path, seal)
    return seal


def validate_approval_integrity(
    *,
    package_path: Path = APPROVAL_PACKAGE,
    record_path: Path = APPROVAL_RECORD,
    mapping_path: Path = ASSET_MAPPING_FILE,
    ledger_path: Path = DECISION_LEDGER,
    seal_path: Path = APPROVAL_INTEGRITY_SEAL,
) -> dict:
    errors = []
    flags = {
        "approval_record_verified": False,
        "package_verified": False,
        "mapping_verified": False,
        "ledger_verified": False,
        "seal_verified": False,
    }
    if transaction_is_pending(_journal_for(mapping_path)):
        errors.append("approval transaction is pending")
        return {**flags, "errors": errors}
    required = {
        "approval package": package_path,
        "approval record": record_path,
        "asset mapping": mapping_path,
        "decision ledger": ledger_path,
        "integrity seal": seal_path,
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        errors.extend(f"{name} is missing" for name in missing)
        return {**flags, "errors": errors}

    package_hash = _sha256_path(package_path)
    record_hash = _sha256_path(record_path)
    mapping_hash = _sha256_path(mapping_path)
    ledger_hash = _sha256_path(ledger_path)
    package = _load_json(package_path)
    record = _load_json(record_path)
    mappings = _load_json(mapping_path)
    ledger = _load_json(ledger_path)
    seal = _load_json(seal_path)
    target = _target_mapping(mappings)
    decision = _target_decision(ledger)
    approved_mappings = _approved_mappings(mappings, ledger)

    package_errors = []
    if package_hash != seal.get("approval_package_hash"):
        package_errors.append("approval package hash does not match integrity seal")
    if package_hash != record.get("package_hash"):
        package_errors.append("approval package hash does not match approval record")
    if package.get("research_asset_id") != TARGET_ASSET_ID:
        package_errors.append("approval package research asset mismatch")
    if package.get("proposed_proxy") != TARGET_PROXY_ID:
        package_errors.append("approval package proxy mismatch")
    flags["package_verified"] = not package_errors
    errors.extend(package_errors)

    record_errors = []
    if record_hash != seal.get("approval_record_hash"):
        record_errors.append("approval record hash does not match integrity seal")
    if record.get("decision_type") != "explicit_human_approval":
        record_errors.append("decision type is not explicit human approval")
    if record.get("explicit_approval_input") != "approved":
        record_errors.append("explicit approval input is missing")
    if record.get("research_asset_id") != TARGET_ASSET_ID:
        record_errors.append("approval record research asset mismatch")
    if record.get("approved_proxy") != TARGET_PROXY_ID:
        record_errors.append("approval record proxy mismatch")
    if record.get("approved_mapping_quality") != APPROVED_MAPPING_QUALITY:
        record_errors.append("approval record mapping quality mismatch")
    if record.get("production_approved") is not False:
        record_errors.append("approval record cannot grant production approval")
    flags["approval_record_verified"] = not record_errors
    errors.extend(record_errors)

    mapping_errors = []
    if mapping_hash != seal.get("current_mapping_hash"):
        mapping_errors.append("current mapping hash does not match integrity seal")
    if target != record.get("mapping_change", {}).get("after"):
        mapping_errors.append("current target mapping row does not match approval record")
    if _hash_json(target) != seal.get("target_mapping_row_hash"):
        mapping_errors.append("target mapping row hash does not match integrity seal")
    if approved_mappings != seal.get("approved_mappings"):
        mapping_errors.append("approved mapping set does not match integrity seal")
    expected_row_hashes = {
        row["research_asset_id"]: _hash_json(row) for row in approved_mappings
    }
    if expected_row_hashes != seal.get("approved_mapping_row_hashes"):
        mapping_errors.append("approved mapping row hashes do not match integrity seal")
    flags["mapping_verified"] = not mapping_errors
    errors.extend(mapping_errors)

    ledger_errors = []
    if ledger_hash != seal.get("current_ledger_hash"):
        ledger_errors.append("current ledger hash does not match integrity seal")
    if decision.get("status") != "approved_for_execution_validation":
        ledger_errors.append("decision ledger approval status mismatch")
    if decision.get("approval_record") != record_path.name:
        ledger_errors.append("decision ledger approval record reference mismatch")
    if decision.get("approved_at") != record.get("decision_date"):
        ledger_errors.append("decision ledger approval date mismatch")
    if decision.get("production_approved") is not False:
        ledger_errors.append("decision ledger cannot grant production approval")
    flags["ledger_verified"] = not ledger_errors
    errors.extend(ledger_errors)

    seal_errors = []
    expected_seal_fields = {
        "available",
        "verification_status",
        "approval_package_hash",
        "approval_record_hash",
        "current_mapping_hash",
        "current_ledger_hash",
        "target_mapping_row_hash",
        "approved_mapping_row_hashes",
        "approved_mappings",
        "approved_asset",
        "approved_proxy",
        "approved_mapping_quality",
        "decision_date",
        "production_approved",
        "errors",
    }
    if set(seal) != expected_seal_fields:
        seal_errors.append("integrity seal schema mismatch")
    if seal.get("verification_status") != "verified" or seal.get("errors") != []:
        seal_errors.append("integrity seal is not verified")
    for field, expected in (
        ("approved_asset", TARGET_ASSET_ID),
        ("approved_proxy", TARGET_PROXY_ID),
        ("approved_mapping_quality", APPROVED_MAPPING_QUALITY),
        ("production_approved", False),
    ):
        if seal.get(field) != expected:
            seal_errors.append(f"integrity seal {field} mismatch")
    if seal.get("decision_date") != record.get("decision_date"):
        seal_errors.append("integrity seal decision date mismatch")
    flags["seal_verified"] = not seal_errors
    errors.extend(seal_errors)
    return {**flags, "errors": errors}


def load_approval_integrity_seal(
    path: Path = APPROVAL_INTEGRITY_SEAL,
) -> dict:
    if transaction_is_pending():
        return {
            "available": False,
            "message": "approval transaction is pending",
        }
    if not path.exists():
        return {"available": False, "message": "approval integrity seal not found"}
    value = _load_json(path)
    value["available"] = True
    value["seal_hash"] = _sha256_path(path)
    value["validation"] = validate_approval_integrity(seal_path=path)
    return value


def _consistency_errors(
    *,
    expected_package_hash: str,
    actual_package_hash: str,
    expected_mapping_hash: str,
    actual_mapping_hash: str,
    decision_date: str,
    record: dict,
    target: dict,
    decision: dict,
    record_name: str,
) -> list[str]:
    errors = []
    if actual_package_hash.lower() != expected_package_hash.lower():
        errors.append("approval package hash mismatch")
    if actual_mapping_hash.lower() != expected_mapping_hash.lower():
        errors.append("mapping after hash mismatch")
    if record.get("package_hash") != actual_package_hash:
        errors.append("approval record package hash mismatch")
    if record.get("mapping_change", {}).get("after") != target:
        errors.append("approval record target mapping row mismatch")
    if record.get("decision_date") != decision_date:
        errors.append("approval record decision date mismatch")
    if record.get("production_approved") is not False:
        errors.append("approval record cannot grant production approval")
    if decision.get("status") != "approved_for_execution_validation":
        errors.append("decision ledger approval status mismatch")
    if decision.get("approval_record") != record_name:
        errors.append("decision ledger approval record reference mismatch")
    if decision.get("approved_at") != decision_date:
        errors.append("decision ledger approval date mismatch")
    if decision.get("production_approved") is not False:
        errors.append("decision ledger cannot grant production approval")
    if target.get("research_asset_id") != TARGET_ASSET_ID:
        errors.append("target mapping research asset mismatch")
    if target.get("primary_execution_proxy") != TARGET_PROXY_ID:
        errors.append("target mapping proxy mismatch")
    if target.get("mapping_quality") != APPROVED_MAPPING_QUALITY:
        errors.append("target mapping quality mismatch")
    return errors


def _target_mapping(mappings: list[dict]) -> dict:
    return next(
        (row for row in mappings if row.get("research_asset_id") == TARGET_ASSET_ID),
        {},
    )


def _target_decision(ledger: dict) -> dict:
    return next(
        (
            row
            for row in ledger.get("decisions", [])
            if row.get("research_asset_id") == TARGET_ASSET_ID
        ),
        {},
    )


def _approved_mappings(mappings: list[dict], ledger: dict) -> list[dict]:
    by_asset = {
        row.get("research_asset_id"): row
        for row in mappings
        if row.get("research_asset_id")
    }
    approved = []
    for decision in ledger.get("decisions", []):
        if decision.get("status") != "approved_for_execution_validation":
            continue
        asset_id = decision.get("research_asset_id")
        mapping = by_asset.get(asset_id, {})
        proxy = mapping.get("primary_execution_proxy")
        if not proxy or proxy != decision.get("proposed_proxy"):
            continue
        approved.append(
            {
                "research_asset_id": asset_id,
                "approved_proxy": proxy,
                "mapping_quality": mapping.get("mapping_quality"),
                "execution_approval": mapping.get(
                    "execution_approval", "quality_policy"
                ),
                "decision_source_report": decision.get("decision_source_report"),
                "production_approved": False,
            }
        )
    return sorted(approved, key=lambda row: row["research_asset_id"])


def _journal_for(mapping_path: Path) -> Path:
    if mapping_path.resolve() == ASSET_MAPPING_FILE.resolve():
        from backtest.execution.approval_transaction import TRANSACTION_JOURNAL

        return TRANSACTION_JOURNAL
    return mapping_path.parent / ".execution_mapping_approval_transaction.json"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_json(value) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
