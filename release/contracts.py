from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re

from decision.current_market.instrument_ids import load_execution_instrument_aliases


SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_PRODUCTION_FIELDS = {
    "order",
    "orders",
    "quantity",
    "quantities",
    "shares",
    "target_price",
    "buy_action",
    "sell_action",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_hash(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def forbidden_field_paths(value: object, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            if str(key).lower() in FORBIDDEN_PRODUCTION_FIELDS:
                found.append(path)
            found.extend(forbidden_field_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden_field_paths(child, f"{prefix}[{index}]"))
    return found


def validate_temporal_contract(market_data_as_of: str, decision_date: str) -> list[str]:
    errors: list[str] = []
    try:
        market_date = date.fromisoformat(market_data_as_of)
        decision = date.fromisoformat(decision_date)
    except ValueError:
        return ["release dates must use ISO YYYY-MM-DD format"]
    if market_date > decision:
        errors.append("market data date must not be after decision date")
    return errors


def validate_artifact_hashes(directory: Path, artifacts: list[dict]) -> list[str]:
    errors: list[str] = []
    for row in artifacts:
        path = directory / row.get("path", "")
        expected = row.get("sha256")
        if not path.exists():
            errors.append(f"release artifact missing: {row.get('path')}")
        elif not isinstance(expected, str) or not SHA256.fullmatch(expected):
            errors.append(f"release artifact hash invalid: {row.get('path')}")
        elif sha256_file(path) != expected:
            errors.append(f"release artifact hash mismatch: {row.get('path')}")
    return errors


def validate_alias_registry(path: Path) -> dict:
    registry = load_execution_instrument_aliases(path)
    return {
        "verified": registry.get("verified") is True,
        "namespace": registry.get("namespace"),
        "alias_count": len(registry.get("aliases", [])),
        "errors": registry.get("errors", []),
    }
