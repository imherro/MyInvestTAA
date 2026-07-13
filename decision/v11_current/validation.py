from __future__ import annotations

from datetime import date
import hashlib
import json
import math

from decision.v11_current.models import V11ValidationResult


CANONICAL_STRATEGY = "V11_PRODUCTION_FUSION"


def canonical_json_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_state_payload(source: dict) -> dict:
    return {
        key: source.get(key)
        for key in (
            "strategy",
            "state_date",
            "period",
            "weights_percent",
            "selected_assets",
            "regime",
            "risk_budget",
            "exposure_decision",
            "target_weights_percent",
            "assumptions",
        )
    }


def canonical_state_hash(source: dict) -> str:
    return canonical_json_hash(canonical_state_payload(source))


def parse_iso_date(value: object, label: str, errors: list[str]) -> date | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} is required")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be a valid ISO date")
        return None


def validate_v11_state_source(source: object, market_data_as_of: str) -> V11ValidationResult:
    errors: list[str] = []
    negative_weights: list[str] = []
    selected_mismatches: list[str] = []
    if not isinstance(source, dict):
        return V11ValidationResult(
            False,
            ["diagnosis V11 current state source must be an object"],
            None,
            None,
            [],
            [],
        )
    if source.get("available") is not True:
        errors.append("diagnosis V11 current state source is unavailable")
    if source.get("strategy") != CANONICAL_STRATEGY:
        errors.append("V11 strategy identity mismatch")

    cutoff = parse_iso_date(market_data_as_of, "market_data_as_of", errors)
    state_date = parse_iso_date(source.get("state_date"), "V11 state_date", errors)
    period = source.get("period")
    if not isinstance(period, dict):
        errors.append("V11 result period must be an object")
        period = {}
    period_start = parse_iso_date(period.get("start"), "V11 result period start", errors)
    period_end = parse_iso_date(period.get("end"), "V11 result period end", errors)
    if period_start and period_end and period_start > period_end:
        errors.append("V11 result period start must not be after end")
    if state_date and period_end and state_date != period_end:
        errors.append("V11 state_date must equal result period end")
    if state_date and cutoff and state_date > cutoff:
        errors.append("V11 state_date is after market data cutoff")

    weights = source.get("weights_percent")
    weight_sum_percent: float | None = None
    weight_sum_fraction: float | None = None
    positive_assets: set[str] = set()
    if not isinstance(weights, dict) or not weights:
        errors.append("V11 weights_percent must be a non-empty object")
    else:
        for asset_id, weight in weights.items():
            if not isinstance(asset_id, str) or not asset_id:
                errors.append("V11 weight asset id must be a non-empty string")
                continue
            if not _finite_number(weight):
                errors.append(f"V11 weight must be finite: {asset_id}")
                continue
            value = float(weight)
            if value < 0:
                negative_weights.append(asset_id)
            if asset_id != "CASH" and value > 0:
                positive_assets.add(asset_id)
        if "CASH" not in weights:
            errors.append("V11 weights_percent must include CASH")
        finite_values = [float(value) for value in weights.values() if _finite_number(value)]
        if len(finite_values) == len(weights):
            weight_sum_percent = round(sum(finite_values), 10)
            weight_sum_fraction = round(weight_sum_percent / 100.0, 12)
            if abs(weight_sum_percent - 100.0) > 0.000001:
                errors.append("V11 weights_percent must sum to 100")
        if negative_weights:
            errors.append("V11 weights_percent contains negative weights")

    selected = source.get("selected_assets")
    if not isinstance(selected, list) or any(
        not isinstance(asset_id, str) or not asset_id for asset_id in selected
    ):
        errors.append("V11 selected_assets must be list[str]")
    else:
        selected_set = set(selected)
        if len(selected_set) != len(selected):
            errors.append("V11 selected_assets must not contain duplicates")
        selected_mismatches = sorted(positive_assets.symmetric_difference(selected_set))
        if selected_mismatches:
            errors.append("V11 selected_assets do not match positive non-cash weights")

    assumptions = source.get("assumptions")
    if not isinstance(assumptions, dict):
        errors.append("V11 assumptions must be an object")
        assumptions = {}
    if assumptions.get("score_version") != "v11":
        errors.append("V11 score_version must be v11")
    if not _finite_number(assumptions.get("max_weight_step")) or float(
        assumptions.get("max_weight_step", 0)
    ) != 10.0:
        errors.append("V11 max_weight_step must equal 10.0")
    if assumptions.get("volatility_adjustment") is not True:
        errors.append("V11 volatility_adjustment must be true")
    from data_pipeline.strategy_diagnosis import V11_ROBUST_EXPOSURE_CONFIG

    if assumptions.get("robust_exposure_config") != V11_ROBUST_EXPOSURE_CONFIG:
        errors.append("V11 robust_exposure_config mismatch")

    expected_state_hash = source.get("source_state_hash")
    try:
        actual_state_hash = canonical_state_hash(source)
    except (TypeError, ValueError):
        actual_state_hash = None
        errors.append("V11 source state cannot be normalized")
    if not isinstance(expected_state_hash, str) or expected_state_hash != actual_state_hash:
        errors.append("V11 source state hash mismatch")

    return V11ValidationResult(
        not errors,
        list(dict.fromkeys(errors)),
        weight_sum_percent,
        weight_sum_fraction,
        negative_weights,
        selected_mismatches,
    )


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
