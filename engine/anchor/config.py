from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from engine.anchor.calculator import calculate_profile_anchor_score
from engine.anchor.models import AssetAnchorProfile


ROOT = Path(__file__).resolve().parents[2]
ANCHOR_PROFILE_FILE = ROOT / "data" / "sample" / "anchor_profiles.json"


@lru_cache(maxsize=1)
def load_anchor_profiles() -> dict[str, AssetAnchorProfile]:
    with ANCHOR_PROFILE_FILE.open("r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        raise ValueError("anchor_profiles.json must contain a list")

    profiles = [calculate_profile_anchor_score(row) for row in rows]
    return {profile.asset_id: profile for profile in profiles}


def load_anchor_profile(asset_id: str) -> AssetAnchorProfile | None:
    return load_anchor_profiles().get(asset_id)

