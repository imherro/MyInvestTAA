from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from engine.asset_registry.loader import ROOT


TRANSACTION_JOURNAL = (
    ROOT / "reports" / "execution_mapping_approval_transaction.json"
)
TRANSACTION_LOCK = ROOT / "reports" / ".execution_mapping_approval.lock"
PENDING_STATES = {"prepared", "applying", "recovery_failed"}


class SimulatedTransactionCrash(BaseException):
    """Test-only crash signal that intentionally bypasses normal rollback."""


def apply_file_transaction(
    updates: dict[Path, bytes],
    *,
    journal_path: Path = TRANSACTION_JOURNAL,
    lock_path: Path | None = None,
    crash_after_replace: int | None = None,
    precondition=None,
) -> dict:
    journal_path = Path(journal_path)
    lock_path = Path(lock_path or _lock_for(journal_path))
    pending = load_transaction_status(journal_path)
    if pending.get("pending"):
        recover_transaction(journal_path=journal_path, lock_path=lock_path)

    with approval_transaction_lock(lock_path):
        if precondition is not None:
            precondition()
        transaction_id = uuid.uuid4().hex
        work_dir = journal_path.parent / ".execution_mapping_approval_txn" / transaction_id
        work_dir.mkdir(parents=True, exist_ok=False)
        entries = []
        for index, (raw_path, after_bytes) in enumerate(updates.items()):
            path = Path(raw_path).resolve()
            existed = path.exists()
            before_bytes = path.read_bytes() if existed else b""
            backup_path = work_dir / f"{index:02d}.before"
            staged_path = work_dir / f"{index:02d}.after"
            if existed:
                _write_fsynced(backup_path, before_bytes)
            _write_fsynced(staged_path, after_bytes)
            entries.append(
                {
                    "path": str(path),
                    "existed_before": existed,
                    "before_hash": _sha256_bytes(before_bytes) if existed else None,
                    "after_hash": _sha256_bytes(after_bytes),
                    "before_backup_path": str(backup_path.resolve()),
                    "staged_after_path": str(staged_path.resolve()),
                    "replaced": False,
                }
            )
        _fsync_directory(work_dir)
        journal = {
            "available": True,
            "transaction_id": transaction_id,
            "status": "prepared",
            "created_at": _now(),
            "updated_at": _now(),
            "commit_marker": False,
            "files": entries,
            "errors": [],
        }
        _write_journal(journal_path, journal)
        journal["status"] = "applying"
        _write_journal(journal_path, journal)

        try:
            for index, entry in enumerate(journal["files"], start=1):
                _replace_staged(entry)
                entry["replaced"] = True
                _write_journal(journal_path, journal)
                if crash_after_replace == index:
                    raise SimulatedTransactionCrash(
                        f"simulated crash after replace {index}"
                    )
            journal["status"] = "committed"
            journal["commit_marker"] = True
            journal["committed_at"] = _now()
            _write_journal(journal_path, journal)
        except Exception as exc:
            journal["errors"].append(str(exc))
            rollback_errors = _rollback_entries(journal["files"])
            journal["errors"].extend(rollback_errors)
            journal["status"] = "recovery_failed" if rollback_errors else "rolled_back"
            journal["rolled_back_at"] = _now()
            journal["commit_marker"] = False
            _write_journal(journal_path, journal)
            if rollback_errors:
                raise RuntimeError(
                    "transaction failed and rollback was incomplete: "
                    + "; ".join(rollback_errors)
                ) from exc
            raise
        finally:
            if journal.get("status") in {"committed", "rolled_back"}:
                shutil.rmtree(work_dir, ignore_errors=True)
        return journal


def recover_transaction(
    *,
    journal_path: Path = TRANSACTION_JOURNAL,
    lock_path: Path | None = None,
    mode: str = "commit",
) -> dict:
    if mode not in {"commit", "rollback"}:
        raise ValueError("recovery mode must be commit or rollback")
    journal_path = Path(journal_path)
    lock_path = Path(lock_path or _lock_for(journal_path))
    journal = _read_journal(journal_path)
    if not journal or journal.get("status") not in PENDING_STATES:
        return load_transaction_status(journal_path)

    with approval_transaction_lock(lock_path, recover_stale=True):
        journal = _read_journal(journal_path)
        if not journal or journal.get("status") not in PENDING_STATES:
            return load_transaction_status(journal_path)
        if mode == "rollback":
            errors = _rollback_entries(journal["files"])
            journal["errors"].extend(errors)
            journal["status"] = "rolled_back" if not errors else "recovery_failed"
            journal["rolled_back_at"] = _now()
            journal["commit_marker"] = False
            _write_journal(journal_path, journal)
            return load_transaction_status(journal_path)

        commit_errors = []
        for entry in journal["files"]:
            path = Path(entry["path"])
            current_hash = _sha256_path(path) if path.exists() else None
            if current_hash == entry["after_hash"]:
                entry["replaced"] = True
                continue
            if current_hash == entry["before_hash"]:
                staged = Path(entry["staged_after_path"])
                if staged.exists() and _sha256_path(staged) == entry["after_hash"]:
                    _replace_staged(entry)
                    entry["replaced"] = True
                    _write_journal(journal_path, journal)
                    continue
            commit_errors.append(f"cannot commit inconsistent file: {path}")
            break

        if commit_errors:
            rollback_errors = _rollback_entries(journal["files"])
            journal["errors"].extend(commit_errors + rollback_errors)
            journal["status"] = "rolled_back" if not rollback_errors else "recovery_failed"
            journal["rolled_back_at"] = _now()
            journal["commit_marker"] = False
        else:
            journal["status"] = "committed"
            journal["commit_marker"] = True
            journal["committed_at"] = _now()
        _write_journal(journal_path, journal)
        work_dir = _work_dir(journal)
        if journal["status"] in {"committed", "rolled_back"} and work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
        return load_transaction_status(journal_path)


def load_transaction_status(path: Path = TRANSACTION_JOURNAL) -> dict:
    journal = _read_journal(Path(path))
    if not journal:
        return {
            "available": True,
            "status": "idle",
            "pending": False,
            "commit_marker": False,
            "errors": [],
        }
    result = dict(journal)
    result["available"] = True
    result["pending"] = journal.get("status") in PENDING_STATES
    return result


def transaction_is_pending(path: Path = TRANSACTION_JOURNAL) -> bool:
    return bool(load_transaction_status(path).get("pending"))


@contextmanager
def approval_transaction_lock(path: Path, *, recover_stale: bool = False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = None
    try:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if not recover_stale or not _stale_lock(path):
                raise RuntimeError("execution mapping approval transaction is locked")
            path.unlink(missing_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        payload = json.dumps({"pid": os.getpid(), "created_at": _now()}).encode("utf-8")
        os.write(descriptor, payload)
        os.fsync(descriptor)
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
            path.unlink(missing_ok=True)


def _replace_staged(entry: dict) -> None:
    staged = Path(entry["staged_after_path"])
    target = Path(entry["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged, target)
    _fsync_path(target)
    _fsync_directory(target.parent)


def _rollback_entries(entries: list[dict]) -> list[str]:
    errors = []
    for entry in reversed(entries):
        path = Path(entry["path"])
        try:
            if entry.get("existed_before"):
                backup = Path(entry["before_backup_path"])
                if not backup.exists():
                    raise FileNotFoundError(f"backup missing: {backup}")
                temporary = path.with_name(f".{path.name}.rollback")
                shutil.copyfile(backup, temporary)
                _fsync_path(temporary)
                os.replace(temporary, path)
                _fsync_path(path)
            else:
                path.unlink(missing_ok=True)
            _fsync_directory(path.parent)
        except Exception as exc:
            errors.append(f"rollback failed for {path}: {exc}")
    return errors


def _write_journal(path: Path, value: dict) -> None:
    value["updated_at"] = _now()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    _write_fsynced(
        temporary,
        (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    os.replace(temporary, path)
    _fsync_path(path)
    _fsync_directory(path.parent)


def _read_journal(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_fsynced(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_path(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _stale_lock(path: Path) -> bool:
    try:
        pid = int(json.loads(path.read_text(encoding="utf-8"))["pid"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return True
    if pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return True
    return False


def _lock_for(journal_path: Path) -> Path:
    if journal_path.resolve() == TRANSACTION_JOURNAL.resolve():
        return TRANSACTION_LOCK
    return journal_path.with_suffix(journal_path.suffix + ".lock")


def _work_dir(journal: dict) -> Path | None:
    files = journal.get("files", [])
    return Path(files[0]["staged_after_path"]).parent if files else None


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
