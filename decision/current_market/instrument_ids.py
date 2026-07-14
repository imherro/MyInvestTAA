from __future__ import annotations

import json
import math
from pathlib import Path
import re

from engine.asset_registry.loader import ROOT


EXECUTION_INSTRUMENT_ALIASES = (
    ROOT / "data" / "universe" / "execution_instrument_aliases.json"
)

CANONICAL_INSTRUMENT_ID = re.compile(r"^[0-9]{6}\.(?:SH|SZ)$")
ALLOWED_INSTRUMENT_TYPES = {"etf", "cash"}


def load_execution_instrument_aliases(
    path: Path | None = None,
) -> dict:
    target = path or EXECUTION_INSTRUMENT_ALIASES
    if not target.exists():
        return {
            "available": False,
            "verified": False,
            "namespace": None,
            "aliases": [],
            "errors": ["execution instrument alias registry is missing"],
        }
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "available": False,
            "verified": False,
            "namespace": None,
            "aliases": [],
            "errors": ["execution instrument alias registry is invalid"],
        }
    errors, _ = _alias_index(value)
    return {
        **value,
        "available": not errors,
        "verified": not errors,
        "errors": errors,
    }


def resolve_canonical_instrument_id(
    asset_id: str,
    alias_registry: dict,
) -> str | None:
    errors, index = _alias_index(alias_registry)
    if errors:
        raise ValueError("; ".join(errors))
    return index.get(asset_id)


def normalize_weight_map(weights: object, alias_registry: dict) -> dict:
    registry_errors, index = _alias_index(alias_registry)
    errors = list(registry_errors)
    unresolved: list[str] = []
    normalization_map: dict[str, str] = {}
    normalized: dict[str, float] = {}
    canonical_sources: dict[str, str] = {}
    original_sum = 0.0
    if not isinstance(weights, dict):
        errors.append("weight map must be an object")
        weights = {}
    for asset_id, weight in weights.items():
        if not isinstance(asset_id, str) or not asset_id:
            errors.append("weight map asset id must be a non-empty string")
            continue
        if not _finite_number(weight):
            errors.append(f"weight must be finite: {asset_id}")
            continue
        value = float(weight)
        original_sum += value
        canonical = index.get(asset_id)
        if canonical is None:
            if value > 0:
                unresolved.append(asset_id)
                errors.append(f"instrument id is unresolved: {asset_id}")
            continue
        previous = canonical_sources.get(canonical)
        if previous is not None and previous != asset_id:
            errors.append(
                f"instrument ID collision: {previous} and {asset_id} -> {canonical}"
            )
            continue
        canonical_sources[canonical] = asset_id
        normalization_map[asset_id] = canonical
        normalized[canonical] = value
    normalized_sum = sum(normalized.values())
    if not errors and abs(original_sum - normalized_sum) > 0.000000000001:
        errors.append("canonical weight sum differs from original weight sum")
    return {
        "verified": not errors,
        "namespace": alias_registry.get("namespace"),
        "weights": normalized,
        "normalization_map": normalization_map,
        "unresolved_ids": sorted(set(unresolved)),
        "errors": list(dict.fromkeys(errors)),
        "original_weight_sum": round(original_sum, 12),
        "canonical_weight_sum": round(normalized_sum, 12),
    }


def _alias_index(registry: object) -> tuple[list[str], dict[str, str]]:
    errors: list[str] = []
    index: dict[str, str] = {}
    canonical_owners: dict[str, str] = {}
    seen_legacy: set[str] = set()
    if not isinstance(registry, dict):
        return ["execution instrument alias registry must be an object"], {}
    if registry.get("namespace") != "tushare_ts_code":
        errors.append("execution instrument alias namespace must be tushare_ts_code")
    aliases = registry.get("aliases")
    if not isinstance(aliases, list) or not aliases:
        return errors + ["execution instrument aliases must be a non-empty list"], {}
    parsed_rows: list[tuple[str, str]] = []
    for position, row in enumerate(aliases):
        if not isinstance(row, dict):
            errors.append(f"execution instrument alias must be an object: {position}")
            continue
        legacy = row.get("legacy_asset_id")
        canonical = row.get("canonical_instrument_id")
        if not isinstance(legacy, str) or not legacy:
            errors.append(f"legacy asset id is invalid: {position}")
            continue
        if not isinstance(canonical, str) or not canonical:
            errors.append(f"canonical instrument id is invalid: {position}")
            continue
        instrument_type = row.get("instrument_type")
        source = row.get("source")
        if instrument_type not in ALLOWED_INSTRUMENT_TYPES:
            errors.append(f"instrument type is invalid: {position}")
        if not isinstance(source, str) or not source.strip():
            errors.append(f"instrument alias source is invalid: {position}")
        if canonical != "CASH" and not CANONICAL_INSTRUMENT_ID.fullmatch(canonical):
            errors.append(f"canonical instrument id format is invalid: {canonical}")
        if canonical == "CASH" and instrument_type != "cash":
            errors.append("CASH instrument type must be cash")
        if canonical != "CASH" and instrument_type != "etf":
            errors.append(f"listed instrument type must be etf: {canonical}")
        if legacy in seen_legacy:
            errors.append(f"legacy asset ID is duplicated: {legacy}")
            continue
        seen_legacy.add(legacy)
        parsed_rows.append((legacy, canonical))
        owner = canonical_owners.get(canonical)
        if owner is not None and owner != legacy:
            errors.append(
                f"canonical instrument ID collision: {owner} and {legacy} -> {canonical}"
            )
            continue
        index[legacy] = canonical
        index[canonical] = canonical
        canonical_owners[canonical] = legacy
    legacy_ids = {legacy for legacy, _ in parsed_rows}
    for legacy, canonical in parsed_rows:
        if canonical in legacy_ids and canonical != legacy:
            errors.append(
                f"alias namespace shadowing is not allowed: {legacy} -> {canonical}"
            )
    return list(dict.fromkeys(errors)), index


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
