from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from engine.asset_registry.models import AssetMapping, ExecutionAsset, ResearchAsset
from engine.asset_registry.validator import (
    validate_execution_assets,
    validate_mappings,
    validate_registry,
    validate_research_assets,
)


ROOT = Path(__file__).resolve().parents[2]
UNIVERSE_DIR = ROOT / "data" / "universe"
RESEARCH_UNIVERSE_FILE = UNIVERSE_DIR / "china_research_universe.json"
EXECUTION_UNIVERSE_FILE = UNIVERSE_DIR / "china_execution_universe.json"
ASSET_MAPPING_FILE = UNIVERSE_DIR / "asset_mapping.json"


@lru_cache(maxsize=2)
def load_research_universe(validate: bool = True) -> list[ResearchAsset]:
    assets = [
        ResearchAsset.from_mapping(row)
        for row in _read_json_list(RESEARCH_UNIVERSE_FILE)
    ]
    if validate:
        _raise_if_errors(validate_research_assets(assets))
    return assets


@lru_cache(maxsize=2)
def load_execution_universe(validate: bool = True) -> list[ExecutionAsset]:
    assets = [
        ExecutionAsset.from_mapping(row)
        for row in _read_json_list(EXECUTION_UNIVERSE_FILE)
    ]
    if validate:
        _raise_if_errors(validate_execution_assets(assets))
    return assets


@lru_cache(maxsize=2)
def load_asset_mappings(validate: bool = True) -> list[AssetMapping]:
    mappings = [
        AssetMapping.from_mapping(row)
        for row in _read_json_list(ASSET_MAPPING_FILE)
    ]
    if validate:
        _raise_if_errors(
            validate_mappings(
                mappings,
                load_research_universe(validate=False),
                load_execution_universe(validate=False),
            )
        )
    return mappings


def load_asset_registry(validate: bool = True) -> dict[str, list]:
    research_assets = load_research_universe(validate=False)
    execution_assets = load_execution_universe(validate=False)
    mappings = load_asset_mappings(validate=False)
    if validate:
        _raise_if_errors(validate_registry(research_assets, execution_assets, mappings))
    return {
        "research_assets": research_assets,
        "execution_assets": execution_assets,
        "mappings": mappings,
    }


def research_assets_by_id() -> dict[str, ResearchAsset]:
    return {asset.asset_id: asset for asset in load_research_universe()}


def execution_assets_by_id() -> dict[str, ExecutionAsset]:
    return {asset.asset_id: asset for asset in load_execution_universe()}


def mappings_by_research_asset() -> dict[str, AssetMapping]:
    return {mapping.research_asset_id: mapping for mapping in load_asset_mappings()}


def clear_asset_registry_cache() -> None:
    load_research_universe.cache_clear()
    load_execution_universe.cache_clear()
    load_asset_mappings.cache_clear()


def _read_json_list(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a list")
    return data


def _raise_if_errors(errors: list[str]) -> None:
    if errors:
        raise ValueError("; ".join(errors))
