from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_FILE = ROOT / "data" / "sample" / "assets.json"


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

