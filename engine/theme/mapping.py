from __future__ import annotations

from engine.theme.models import ThemeMapping


DEFAULT_THEME_MAPPING = {
    "510300": "large_cap",
    "510500": "mid_cap",
    "512100": "small_cap",
    "159915": "growth",
    "588000": "innovation",
    "512890": "dividend",
    "515100": "dividend",
    "515080": "dividend",
    "512760": "semiconductor",
    "515790": "new_energy",
    "516160": "new_energy",
    "512170": "healthcare",
    "512010": "healthcare",
    "512690": "consumer",
    "512800": "financial",
    "512880": "brokerage",
    "512660": "defense",
    "512400": "cyclical",
    "518880": "gold",
    "511010": "government_bond",
}


def theme_for_asset(asset_id: str) -> str:
    return DEFAULT_THEME_MAPPING.get(asset_id, "unclassified")


def load_theme_mapping(asset_ids: list[str] | None = None) -> list[dict]:
    values = asset_ids or sorted(DEFAULT_THEME_MAPPING)
    return [
        ThemeMapping(asset=asset_id, theme=theme_for_asset(asset_id)).as_dict()
        for asset_id in values
    ]
