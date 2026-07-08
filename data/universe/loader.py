from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


UNIVERSE_FILE = Path(__file__).resolve().parent / "china_etf_universe.json"


@lru_cache(maxsize=1)
def load_china_etf_universe() -> list[dict]:
    with UNIVERSE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("china_etf_universe.json must contain a list")
    for item in data:
        missing = {"id", "name", "category", "asset_class"} - set(item)
        if missing:
            raise ValueError(f"universe item missing fields: {sorted(missing)}")
    return data


def universe_asset_ids() -> list[str]:
    return [item["id"] for item in load_china_etf_universe()]


def universe_by_category() -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in load_china_etf_universe():
        grouped.setdefault(item["category"], []).append(item)
    return grouped
