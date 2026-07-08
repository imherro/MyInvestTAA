from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_FILE = ROOT / "data" / "sample" / "assets.json"
HISTORY_FILE = ROOT / "data" / "sample" / "history" / "prices.json"


@lru_cache(maxsize=1)
def load_assets() -> list[dict]:
    with ASSET_FILE.open("r", encoding="utf-8") as f:
        assets = json.load(f)

    if not isinstance(assets, list):
        raise ValueError("assets.json must contain a list")

    for asset in assets:
        required = {"id", "name", "category", "anchor_score", "prices"}
        missing = sorted(required - set(asset))
        if missing:
            raise ValueError(f"asset {asset.get('id', '<unknown>')} missing fields: {missing}")

    return assets


@lru_cache(maxsize=1)
def load_price_histories() -> dict[str, list[dict]]:
    with HISTORY_FILE.open("r", encoding="utf-8") as f:
        histories = json.load(f)

    if not isinstance(histories, dict):
        raise ValueError("prices.json must contain an object keyed by asset id")
    return histories


def load_price_history(asset_id: str) -> list[dict]:
    histories = load_price_histories()
    if asset_id not in histories:
        raise ValueError(f"history not found for asset_id: {asset_id}")
    return histories[asset_id]

