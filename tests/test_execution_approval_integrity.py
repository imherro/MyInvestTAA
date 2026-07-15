import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backtest.execution.approval_integrity import (
    APPROVAL_INTEGRITY_SEAL,
    APPROVAL_RECORD,
    load_approval_integrity_seal,
    validate_approval_integrity,
)
from backtest.execution.approval_package import (
    APPROVAL_PACKAGE,
    DECISION_LEDGER,
    TARGET_ASSET_ID,
)
from backtest.execution.approval_transaction import (
    SimulatedTransactionCrash,
    apply_file_transaction,
    approval_transaction_lock,
    load_transaction_status,
    recover_transaction,
)
from backtest.execution.mapping_application import APPROVED_NOTES
from backtest.execution.models import ExecutionPrice
from backtest.execution.shadow_portfolio import build_execution_aware_shadow_portfolio
from backtest.execution.shadow_report import load_execution_aware_shadow_portfolio
from engine.asset_registry.loader import ASSET_MAPPING_FILE
from engine.asset_registry.models import AssetMapping


CLIENT = TestClient(app)
SEAL = load_approval_integrity_seal()
SHADOW = load_execution_aware_shadow_portfolio()
RECORD = json.loads(APPROVAL_RECORD.read_text(encoding="utf-8"))
LEDGER = json.loads(DECISION_LEDGER.read_text(encoding="utf-8"))
MAPPINGS = json.loads(ASSET_MAPPING_FILE.read_text(encoding="utf-8"))
VALID_INTEGRITY = {
    "approval_record_verified": True,
    "package_verified": True,
    "mapping_verified": True,
    "ledger_verified": True,
    "seal_verified": True,
    "errors": [],
}


@pytest.mark.parametrize(
    "field",
    [
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
        "seal_hash",
        "validation",
    ],
)
def test_current_integrity_seal_has_required_field(field):
    assert field in SEAL


@pytest.mark.parametrize(
    "field",
    [
        "approval_record_verified",
        "package_verified",
        "mapping_verified",
        "ledger_verified",
        "seal_verified",
    ],
)
def test_current_integrity_validation_passes_each_gate(field):
    assert SEAL["validation"][field] is True
    assert SEAL["validation"]["errors"] == []


@pytest.mark.parametrize(
    "field",
    [
        "research_report_hash",
        "mapping_registry_hash",
        "decision_ledger_hash",
        "approval_record_hash",
        "approval_seal_hash",
        "price_manifest_hash",
        "verified",
        "errors",
    ],
)
def test_shadow_snapshot_has_required_hash_field(field):
    assert field in SHADOW["snapshot_integrity"]


@pytest.mark.parametrize("proxy", ["510500.SH", "512760.SH", "588000.SH"])
@pytest.mark.parametrize(
    "field",
    [
        "requested_as_of",
        "actual_price_date",
        "staleness_calendar_days",
        "usable",
    ],
)
def test_current_shadow_price_as_of_is_auditable(proxy, field):
    assert field in SHADOW["price_as_of_by_proxy"][proxy]


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("approved_asset", TARGET_ASSET_ID),
        ("approved_proxy", "512760.SH"),
        ("approved_mapping_quality", "medium"),
        ("production_approved", False),
        ("decision_date", "2026-07-13"),
    ],
)
def test_integrity_seal_identity_is_fixed(field, expected):
    assert SEAL[field] == expected


def _integrity_copies(tmp_path):
    paths = {}
    for name, source in {
        "package": APPROVAL_PACKAGE,
        "record": APPROVAL_RECORD,
        "mapping": ASSET_MAPPING_FILE,
        "ledger": DECISION_LEDGER,
        "seal": APPROVAL_INTEGRITY_SEAL,
    }.items():
        target = tmp_path / source.name
        shutil.copyfile(source, target)
        paths[name] = target
    return paths


@pytest.mark.parametrize("component", ["package", "record", "mapping", "ledger", "seal"])
def test_integrity_validation_fails_closed_on_component_drift(tmp_path, component):
    paths = _integrity_copies(tmp_path)
    value = json.loads(paths[component].read_text(encoding="utf-8"))
    if isinstance(value, list):
        value[0]["notes"] = "drifted"
    else:
        value["drift_marker"] = component
    paths[component].write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    result = validate_approval_integrity(
        package_path=paths["package"],
        record_path=paths["record"],
        mapping_path=paths["mapping"],
        ledger_path=paths["ledger"],
        seal_path=paths["seal"],
    )
    assert result["errors"]
    assert not all(result[field] for field in VALID_INTEGRITY if field != "errors")


def _transaction_files(tmp_path):
    files = [tmp_path / f"target-{index}.json" for index in range(3)]
    before = {}
    after = {}
    for index, path in enumerate(files):
        before[path] = f"before-{index}\n".encode()
        after[path] = f"after-{index}\n".encode()
        path.write_bytes(before[path])
    return files, before, after


@pytest.mark.parametrize("crash_point", [1, 2, 3])
def test_crash_point_recovery_can_finish_commit(tmp_path, crash_point):
    files, _, after = _transaction_files(tmp_path)
    journal = tmp_path / "journal.json"
    with pytest.raises(SimulatedTransactionCrash):
        apply_file_transaction(
            after, journal_path=journal, crash_after_replace=crash_point
        )
    assert load_transaction_status(journal)["pending"] is True
    result = recover_transaction(journal_path=journal, mode="commit")
    assert result["status"] == "committed"
    assert result["commit_marker"] is True
    assert all(path.read_bytes() == after[path] for path in files)


@pytest.mark.parametrize("crash_point", [1, 2, 3])
def test_crash_point_recovery_can_restore_before_files(tmp_path, crash_point):
    files, before, after = _transaction_files(tmp_path)
    journal = tmp_path / "journal.json"
    with pytest.raises(SimulatedTransactionCrash):
        apply_file_transaction(
            after, journal_path=journal, crash_after_replace=crash_point
        )
    result = recover_transaction(journal_path=journal, mode="rollback")
    assert result["status"] == "rolled_back"
    assert result["commit_marker"] is False
    assert all(path.read_bytes() == before[path] for path in files)


@pytest.mark.parametrize(
    "field",
    [
        "path",
        "existed_before",
        "before_hash",
        "after_hash",
        "before_backup_path",
        "staged_after_path",
        "replaced",
    ],
)
def test_transaction_journal_records_each_file_field(tmp_path, field):
    _, _, after = _transaction_files(tmp_path)
    journal = tmp_path / "journal.json"
    result = apply_file_transaction(after, journal_path=journal)
    assert all(field in entry for entry in result["files"])


def test_transaction_lock_rejects_concurrent_approval(tmp_path):
    lock = tmp_path / "approval.lock"
    with approval_transaction_lock(lock):
        with pytest.raises(RuntimeError, match="locked"):
            with approval_transaction_lock(lock):
                pass


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("available", True),
        ("status", "idle"),
        ("pending", False),
        ("commit_marker", False),
        ("errors", []),
    ],
)
def test_missing_transaction_journal_is_idle(tmp_path, field, expected):
    assert load_transaction_status(tmp_path / "missing.json")[field] == expected


def _shadow_report(*, integrity=None, prices=None, as_of="2026-01-11"):
    mapping = AssetMapping("A", "A", "ETF", ["ETF"], "medium")
    return build_execution_aware_shadow_portfolio(
        {
            "available": True,
            "strategy": "RESEARCH_TAA_MVP",
            "period": {"end": as_of},
            "monthly_allocations": [
                {"date": as_of, "weights": {"A": 0.4, "CASH": 0.6}}
            ],
        },
        [mapping],
        {"ETF": prices or []},
        {
            "provenance_verified": True,
            "provider": "tushare",
            "return_basis": "qfq",
            "end": as_of,
        },
        {
            "decisions": [
                {
                    "research_asset_id": "A",
                    "status": "approved_for_execution_validation",
                }
            ]
        },
        RECORD,
        integrity or VALID_INTEGRITY,
        {"verified": True, "errors": []},
    )


@pytest.mark.parametrize(
    "failed_gate",
    [
        "approval_record_verified",
        "package_verified",
        "mapping_verified",
        "ledger_verified",
        "seal_verified",
    ],
)
def test_shadow_fails_closed_when_approval_gate_fails(failed_gate):
    integrity = dict(VALID_INTEGRITY)
    integrity[failed_gate] = False
    integrity["errors"] = [failed_gate]
    report = _shadow_report(
        integrity=integrity,
        prices=[ExecutionPrice("ETF", "2026-01-09", 1.0)],
    )
    assert report["available"] is False
    assert failed_gate in report["errors"]
    assert "execution_weights" not in report


def test_weekend_as_of_uses_previous_trading_day():
    report = _shadow_report(
        prices=[ExecutionPrice("ETF", "2026-01-09", 1.0)]
    )
    assert report["execution_weights"]["ETF"] == pytest.approx(0.4)
    assert report["price_as_of_by_proxy"]["ETF"] == {
        "requested_as_of": "2026-01-11",
        "actual_price_date": "2026-01-09",
        "staleness_calendar_days": 2,
        "usable": True,
    }


def test_future_price_is_never_used():
    report = _shadow_report(
        prices=[ExecutionPrice("ETF", "2026-01-12", 1.0)]
    )
    assert report["cash_breakdown"]["missing_price_cash"] == pytest.approx(0.4)
    assert report["price_as_of_by_proxy"]["ETF"]["actual_price_date"] is None


@pytest.mark.parametrize(
    ("price_date", "usable"),
    [
        ("2026-01-11", True),
        ("2026-01-10", True),
        ("2026-01-09", True),
        ("2026-01-08", True),
        ("2026-01-07", True),
        ("2026-01-06", True),
        ("2026-01-05", False),
    ],
)
def test_price_staleness_threshold_is_five_calendar_days(price_date, usable):
    report = _shadow_report(prices=[ExecutionPrice("ETF", price_date, 1.0)])
    assert report["price_as_of_by_proxy"]["ETF"]["usable"] is usable
    if usable:
        assert report["execution_weights"]["ETF"] == pytest.approx(0.4)
    else:
        assert report["cash_breakdown"]["missing_price_cash"] == pytest.approx(0.4)


@pytest.mark.parametrize(
    "needle",
    [
        "--expected-package-hash",
        "--expected-mapping-hash",
        "--explicit-approval",
        "--decision-date",
    ],
)
def test_approval_cli_declares_all_required_inputs(needle):
    source = Path("scripts/apply_execution_mapping_approval.py").read_text(
        encoding="utf-8"
    )
    assert needle in source


def test_approval_cli_rejects_missing_expected_package_hash():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/apply_execution_mapping_approval.py",
            "--explicit-approval",
            "approved",
            "--expected-mapping-hash",
            "0" * 64,
            "--decision-date",
            "2026-07-13",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "--expected-package-hash" in result.stderr


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("primary_execution_proxy", "512760.SH"),
        ("execution_proxies", ["512760.SH"]),
        ("mapping_quality", "medium"),
        ("notes", APPROVED_NOTES),
    ],
)
def test_current_approved_mapping_remains_unchanged(field, expected):
    row = next(item for item in MAPPINGS if item["research_asset_id"] == TARGET_ASSET_ID)
    assert row[field] == expected


@pytest.mark.parametrize(
    ("asset_id", "status"),
    [
        ("931688CNY010.CSI", "588200.SH"),
        ("H00805.CSI", "512400.SH"),
        ("H20590.CSI", "562500.SH"),
        ("H21152.CSI", "159992.SZ"),
    ],
)
def test_user_authorized_ledger_decisions_are_sealed(asset_id, status):
    row = next(item for item in LEDGER["decisions"] if item["research_asset_id"] == asset_id)
    assert row["status"] == "approved_for_execution_validation"
    assert row["proposed_proxy"] == status
    assert row["production_approved"] is False


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/research/execution-mapping-approval-integrity",
        "/api/research/execution-mapping-transaction-status",
    ],
)
def test_integrity_and_transaction_apis_are_read_only_reports(endpoint):
    response = CLIENT.get(endpoint)
    assert response.status_code == 200
    assert response.json()["available"] is True


def test_shadow_page_displays_integrity_sections_and_warning():
    text = CLIENT.get("/shadow-portfolio").text
    for section in (
        "Approval Integrity",
        "Snapshot Hashes",
        "Price As-Of by Proxy",
        "Transaction Status",
    ):
        assert section in text
    assert "not a production portfolio or trading instruction" in text


def test_current_shadow_integrity_and_weights_remain_stable():
    assert SHADOW["snapshot_integrity"]["verified"] is True
    assert SHADOW["approval_integrity"] == VALID_INTEGRITY
    assert SHADOW["execution_weights"] == {
        "510500.SH": 0.25,
        "512760.SH": 0.1,
        "588000.SH": 0.25,
        "588200.SH": 0.1,
        "CASH": 0.3,
    }
    assert hashlib.sha256(ASSET_MAPPING_FILE.read_bytes()).hexdigest() == SEAL[
        "current_mapping_hash"
    ]


def test_shadow_loader_fails_closed_when_snapshot_source_drifts(tmp_path, monkeypatch):
    import backtest.research.report as research_report

    drifted = tmp_path / "research_backtest_report.json"
    shutil.copyfile(research_report.RESEARCH_BACKTEST_REPORT, drifted)
    drifted.write_bytes(drifted.read_bytes() + b" ")
    monkeypatch.setattr(research_report, "RESEARCH_BACKTEST_REPORT", drifted)
    result = load_execution_aware_shadow_portfolio()
    assert result["available"] is False
    assert "research_report_hash" in " ".join(result["errors"])


def test_shadow_loader_is_unavailable_during_pending_transaction(monkeypatch):
    monkeypatch.setattr(
        "backtest.execution.shadow_report.transaction_is_pending", lambda: True
    )
    result = load_execution_aware_shadow_portfolio()
    assert result == {"available": False, "message": "approval transaction is pending"}


def test_rollback_failure_is_reported_as_recovery_failed(tmp_path, monkeypatch):
    import backtest.execution.approval_transaction as transaction

    _, _, after = _transaction_files(tmp_path)
    journal = tmp_path / "journal.json"
    monkeypatch.setattr(
        transaction, "_replace_staged", lambda entry: (_ for _ in ()).throw(OSError("write failed"))
    )
    monkeypatch.setattr(
        transaction, "_rollback_entries", lambda entries: ["backup restore failed"]
    )
    with pytest.raises(RuntimeError, match="rollback was incomplete"):
        apply_file_transaction(after, journal_path=journal)
    status = load_transaction_status(journal)
    assert status["status"] == "recovery_failed"
    assert "backup restore failed" in status["errors"]
