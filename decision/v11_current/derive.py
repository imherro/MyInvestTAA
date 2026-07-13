from __future__ import annotations

from copy import deepcopy

from decision.v11_current.validation import (
    canonical_json_hash,
    validate_v11_state_source,
)


NON_TRADING_WARNING = (
    "This is an offline V11 model allocation snapshot, not an order or trading instruction."
)

SNAPSHOT_PAYLOAD_FIELDS = (
    "strategy",
    "as_of",
    "source_state_date",
    "allocation",
    "allocation_percent",
    "equity_weight",
    "cash_weight",
    "selected_assets",
    "regime",
    "risk_budget",
    "exposure_decision",
    "target_weights_percent",
    "assumptions",
    "constraint_checks",
    "available",
    "status",
    "production_candidate",
    "production_actionable",
    "trading_instruction",
)


def derive_v11_snapshot_fields(source: dict) -> dict:
    """Derive every snapshot business field from one validated V11 state source."""
    weights_percent = deepcopy(source.get("weights_percent", {}))
    allocation = {
        asset_id: round(float(weight) / 100.0, 12)
        for asset_id, weight in weights_percent.items()
        if isinstance(weight, (int, float)) and not isinstance(weight, bool)
    }
    cash_weight = allocation.get("CASH")
    equity_weight = (
        round(1.0 - cash_weight, 12) if cash_weight is not None else None
    )
    selected_assets = sorted(
        asset_id
        for asset_id, weight in allocation.items()
        if asset_id != "CASH" and weight > 0
    )
    validation = validate_v11_state_source(
        source, str(source.get("state_date") or "")
    )
    allocation_sum = round(sum(allocation.values()), 12) if allocation else None
    return {
        "allocation_percent": weights_percent,
        "allocation": allocation,
        "equity_weight": equity_weight,
        "cash_weight": cash_weight,
        "selected_assets": selected_assets,
        "regime": deepcopy(source.get("regime", {})),
        "risk_budget": deepcopy(source.get("risk_budget", {})),
        "exposure_decision": deepcopy(source.get("exposure_decision", {})),
        "target_weights_percent": deepcopy(
            source.get("target_weights_percent", {})
        ),
        "assumptions": deepcopy(source.get("assumptions", {})),
        "constraint_checks": {
            "weight_sum_percent": validation.weight_sum_percent,
            "weight_sum_fraction": allocation_sum,
            "negative_weights": list(validation.negative_weights),
            "selected_asset_mismatches": list(
                validation.selected_asset_mismatches
            ),
            "violations": list(validation.errors),
        },
    }


def canonical_snapshot_payload(snapshot: dict) -> dict:
    return {field: snapshot.get(field) for field in SNAPSHOT_PAYLOAD_FIELDS}


def snapshot_payload_hash(snapshot: dict) -> str:
    return canonical_json_hash(canonical_snapshot_payload(snapshot))
