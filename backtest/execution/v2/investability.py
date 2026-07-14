from __future__ import annotations

import json
from pathlib import Path

from engine.asset_registry.loader import ROOT


METADATA_PATH = ROOT / "data" / "universe" / "execution_instrument_metadata.json"


def load_instrument_metadata(path: Path | None = None) -> dict[str, dict]:
    target = path or METADATA_PATH
    rows = json.loads(target.read_text(encoding="utf-8"))
    result = {row["instrument_id"]: row for row in rows}
    if len(result) != len(rows) or any(row.get("verified") is not True for row in rows):
        raise ValueError("unique, verified execution instrument metadata is required")
    return result


def investability_state(date: str, metadata: dict, prices: dict[str, float], last_price_date: str | None = None) -> dict:
    listing = metadata.get("listing_date")
    investable = metadata.get("investable_start_date")
    if not metadata.get("verified"):
        state = "metadata_unverified"
    elif listing and date < listing:
        state = "before_listing"
    elif investable and date < investable:
        state = "before_investable_start"
    elif date in prices:
        state = "price_available"
    else:
        state = "unknown_missing_price"
    current = state == "price_available"
    can_value = current or last_price_date is not None
    return {
        "state": state,
        "can_enter": current,
        "can_exit": current,
        "can_value": can_value,
        "price_date": date if current else last_price_date,
        "reason": None if current else state,
    }


def build_investability_timeline(dates: list[str], metadata: dict[str, dict], price_maps: dict[str, dict[str, float]]) -> list[dict]:
    rows = []
    for instrument_id in sorted(metadata):
        last_price_date = None
        prices = price_maps.get(instrument_id, {})
        for date in dates:
            state = investability_state(date, metadata[instrument_id], prices, last_price_date)
            if state["state"] == "price_available":
                last_price_date = date
            rows.append({"date": date, "instrument_id": instrument_id, **state})
    return rows
