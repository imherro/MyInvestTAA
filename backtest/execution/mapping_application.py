from __future__ import annotations

import copy
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
from backtest.execution.approval_transaction import (
    TRANSACTION_JOURNAL,
    apply_file_transaction,
    transaction_is_pending,
)
from engine.asset_registry.loader import ASSET_MAPPING_FILE, ROOT, clear_asset_registry_cache

APPROVAL_RECORD = ROOT / "reports" / "execution_mapping_approval_record.json"
APPROVED_MAPPING_QUALITY = "medium"
APPROVED_NOTES = (
    "Human-approved for execution validation and shadow use. Broader "
    "semiconductor-chip proxy; not a direct materials-equipment index tracker."
)


def apply_human_approved_mapping(
    *,
    explicit_approval: str,
    expected_package_hash: str,
    expected_mapping_hash: str,
    decision_date: str,
    mapping_path: Path = ASSET_MAPPING_FILE,
    package_path: Path = APPROVAL_PACKAGE,
    ledger_path: Path = DECISION_LEDGER,
    record_path: Path = APPROVAL_RECORD,
    transaction_journal_path: Path | None = None,
) -> dict:
    mapping_before_bytes = mapping_path.read_bytes()
    mapping_before_text = mapping_before_bytes.decode("utf-8")
    mapping_before_hash = _sha256_bytes(mapping_before_bytes)
    package_bytes = package_path.read_bytes()
    package_hash = _sha256_bytes(package_bytes)
    package = json.loads(package_bytes.decode("utf-8"))
    mappings = json.loads(mapping_before_text)
    ledger_before_bytes = ledger_path.read_bytes()
    ledger_before_text = ledger_before_bytes.decode("utf-8")
    ledger = json.loads(ledger_before_text)

    _validate_application(
        explicit_approval=explicit_approval,
        expected_package_hash=expected_package_hash,
        actual_package_hash=package_hash,
        expected_mapping_hash=expected_mapping_hash,
        mapping_before_hash=mapping_before_hash,
        package=package,
        mappings=mappings,
    )

    before_rows = copy.deepcopy(mappings)
    target = next(
        row for row in mappings if row["research_asset_id"] == TARGET_ASSET_ID
    )
    before_target = copy.deepcopy(target)
    target.update(
        {
            "primary_execution_proxy": TARGET_PROXY_ID,
            "execution_proxies": [TARGET_PROXY_ID],
            "mapping_quality": APPROVED_MAPPING_QUALITY,
            "notes": APPROVED_NOTES,
        }
    )
    changed_assets = _changed_asset_ids(before_rows, mappings)
    if changed_assets != [TARGET_ASSET_ID]:
        raise ValueError(f"unexpected mapping changes: {changed_assets}")

    mapping_after_text = _with_source_newlines(
        _render_mapping_registry(mappings), mapping_before_bytes
    )
    mapping_after_bytes = mapping_after_text.encode("utf-8")
    mapping_after_hash = _sha256_bytes(mapping_after_bytes)
    record = {
        "available": True,
        "research_asset_id": TARGET_ASSET_ID,
        "approved_proxy": TARGET_PROXY_ID,
        "approved_mapping_quality": APPROVED_MAPPING_QUALITY,
        "decision_type": "explicit_human_approval",
        "explicit_approval_input": explicit_approval,
        "decision_date": decision_date,
        "source_package": package_path.name,
        "package_hash": package_hash,
        "expected_package_hash_input": expected_package_hash,
        "actual_package_hash": package_hash,
        "expected_mapping_hash_input": expected_mapping_hash,
        "actual_mapping_before_hash": mapping_before_hash,
        "mapping_before_hash": mapping_before_hash,
        "mapping_after_hash": mapping_after_hash,
        "changed_asset_ids": changed_assets,
        "mapping_change": {"before": before_target, "after": copy.deepcopy(target)},
        "limitations": [
            "The ETF tracks a broader semiconductor-chip index.",
            "The mapping is approved for execution validation and shadow use only.",
        ],
        "production_approved": False,
    }
    updated_ledger = _approved_ledger(ledger, record_path.name, decision_date)
    ledger_after_text = _with_source_newlines(
        json.dumps(updated_ledger, ensure_ascii=False, indent=2) + "\n",
        ledger_before_bytes,
    )
    record_text = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    journal_path = transaction_journal_path or _journal_for(mapping_path)
    apply_file_transaction(
        {
            mapping_path: mapping_after_bytes,
            ledger_path: ledger_after_text.encode("utf-8"),
            record_path: record_text.encode("utf-8"),
        },
        journal_path=journal_path,
        precondition=lambda: _verify_locked_inputs(
            mapping_path,
            package_path,
            mapping_before_hash,
            expected_package_hash,
        ),
    )
    if _sha256_path(mapping_path) != mapping_after_hash:
        raise RuntimeError("mapping transaction committed with unexpected hash")
    if _sha256_path(package_path) != expected_package_hash.lower():
        raise RuntimeError("approval package changed during transaction")

    clear_asset_registry_cache()
    return record


def validate_approval_record(
    record: dict,
    package_path: Path = APPROVAL_PACKAGE,
    *,
    record_path: Path = APPROVAL_RECORD,
    mapping_path: Path = ASSET_MAPPING_FILE,
    ledger_path: Path = DECISION_LEDGER,
    seal_path: Path | None = None,
) -> dict:
    errors = []
    if record.get("decision_type") != "explicit_human_approval":
        errors.append("decision type is not explicit human approval")
    if record.get("explicit_approval_input") != "approved":
        errors.append("explicit approval input is missing")
    if record.get("package_hash") != _sha256_path(package_path):
        errors.append("approval package hash mismatch")
    if record.get("research_asset_id") != TARGET_ASSET_ID:
        errors.append("approval record research asset mismatch")
    if record.get("approved_proxy") != TARGET_PROXY_ID:
        errors.append("approval record proxy mismatch")
    if record.get("approved_mapping_quality") != APPROVED_MAPPING_QUALITY:
        errors.append("approval record mapping quality mismatch")
    if record.get("production_approved") is not False:
        errors.append("approval record cannot grant production approval")
    from backtest.execution.approval_integrity import (
        APPROVAL_INTEGRITY_SEAL,
        validate_approval_integrity,
    )

    integrity = validate_approval_integrity(
        package_path=package_path,
        record_path=record_path,
        mapping_path=mapping_path,
        ledger_path=ledger_path,
        seal_path=seal_path or APPROVAL_INTEGRITY_SEAL,
    )
    errors.extend(integrity["errors"])
    return {
        **integrity,
        "approval_record_verified": not errors,
        "errors": list(dict.fromkeys(errors)),
    }


def load_mapping_approval_record(path: Path | None = None) -> dict:
    target = path or APPROVAL_RECORD
    if transaction_is_pending():
        return {"available": False, "message": "approval transaction is pending"}
    if not target.exists():
        return {"available": False, "message": "mapping approval record not found"}
    record = json.loads(target.read_text(encoding="utf-8"))
    record["available"] = True
    return record


def _validate_application(
    *,
    explicit_approval: str,
    expected_package_hash: str,
    actual_package_hash: str,
    expected_mapping_hash: str,
    mapping_before_hash: str,
    package: dict,
    mappings: list[dict],
) -> None:
    errors = []
    if explicit_approval != "approved":
        errors.append("explicit human approval was not supplied")
    if not expected_package_hash:
        errors.append("expected approval package hash is required")
    elif expected_package_hash.lower() != actual_package_hash.lower():
        errors.append("approval package hash mismatch")
    if expected_mapping_hash.lower() != mapping_before_hash.lower():
        errors.append("full asset mapping baseline hash mismatch")
    if not package.get("available"):
        errors.append("approval package is unavailable")
    if not package.get("ready_for_explicit_human_decision"):
        errors.append("approval package is not ready for explicit decision")
    if not package.get("requires_manual_approval"):
        errors.append("approval package manual approval flag is missing")
    if not package.get("dataset_provenance", {}).get("provenance_verified"):
        errors.append("dataset provenance is not verified")
    exact = package.get("exact_drawdown_attribution", {}).get(
        "selective_reconciliation", {}
    )
    if exact.get("reconciliation_error", 1) > 0.000001:
        errors.append("attribution reconciliation error exceeds tolerance")
    if abs(exact.get("residual", 1)) > 0.000001:
        errors.append("attribution residual exceeds tolerance")
    if exact.get("approximate") is not False:
        errors.append("attribution is approximate")
    if package.get("semantic_evidence", {}).get("semantic_quality") != "acceptable":
        errors.append("semantic quality is not acceptable")
    if package.get("research_asset_id") != TARGET_ASSET_ID:
        errors.append("approval package research asset mismatch")
    if package.get("proposed_proxy") != TARGET_PROXY_ID:
        errors.append("approval package proxy mismatch")
    target = next(
        (row for row in mappings if row.get("research_asset_id") == TARGET_ASSET_ID),
        None,
    )
    if not target:
        errors.append("target mapping row is missing")
    elif not (
        target.get("primary_execution_proxy") is None
        and target.get("mapping_quality") == "none"
        and target.get("execution_proxies") == []
    ):
        errors.append("target mapping is no longer in the approved baseline state")
    if errors:
        raise ValueError("; ".join(errors))


def _approved_ledger(ledger: dict, record_name: str, decision_date: str) -> dict:
    updated = copy.deepcopy(ledger)
    before = copy.deepcopy(updated.get("decisions", []))
    target = next(
        row
        for row in updated["decisions"]
        if row["research_asset_id"] == TARGET_ASSET_ID
    )
    target.update(
        {
            "status": "approved_for_execution_validation",
            "decision_reason": (
                "Explicitly human-approved for execution validation and shadow use; "
                "not approved for production trading."
            ),
            "approval_record": record_name,
            "approved_at": decision_date,
            "production_approved": False,
        }
    )
    changed = [
        after["research_asset_id"]
        for old, after in zip(before, updated["decisions"])
        if old != after
    ]
    if changed != [TARGET_ASSET_ID]:
        raise ValueError(f"unexpected decision ledger changes: {changed}")
    return updated


def _changed_asset_ids(before: list[dict], after: list[dict]) -> list[str]:
    old = {row["research_asset_id"]: row for row in before}
    new = {row["research_asset_id"]: row for row in after}
    return sorted(asset_id for asset_id in old | new if old.get(asset_id) != new.get(asset_id))


def _render_mapping_registry(rows: list[dict]) -> str:
    lines = ["["]
    for index, row in enumerate(rows):
        lines.append("  {")
        items = list(row.items())
        for field_index, (key, value) in enumerate(items):
            comma = "," if field_index < len(items) - 1 else ""
            lines.append(
                f"    {json.dumps(key, ensure_ascii=False)}: "
                f"{json.dumps(value, ensure_ascii=False)}{comma}"
            )
        lines.append("  }" + ("," if index < len(rows) - 1 else ""))
    lines.append("]")
    return "\n".join(lines) + "\n"


def _with_source_newlines(value: str, source: bytes) -> str:
    return value.replace("\n", "\r\n") if b"\r\n" in source else value


def _atomic_write_text(path: Path, value: str) -> None:
    _atomic_write_bytes(path, value.encode("utf-8"))


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _journal_for(mapping_path: Path) -> Path:
    if mapping_path.resolve() == ASSET_MAPPING_FILE.resolve():
        return TRANSACTION_JOURNAL
    return mapping_path.parent / ".execution_mapping_approval_transaction.json"


def _verify_locked_inputs(
    mapping_path: Path,
    package_path: Path,
    expected_mapping_hash: str,
    expected_package_hash: str,
) -> None:
    if _sha256_path(mapping_path) != expected_mapping_hash.lower():
        raise ValueError("full asset mapping changed before transaction lock")
    if _sha256_path(package_path) != expected_package_hash.lower():
        raise ValueError("approval package changed before transaction lock")
