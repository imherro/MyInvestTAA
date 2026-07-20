from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXPECTED_TIER_COUNTS = {"A": 7, "B": 12, "C": 13}
ALLOWED_ASSET_GROUPS = {"broad_base", "style", "industry"}
ALLOWED_VERIFICATION_STATUSES = {"verified", "unverified", "unavailable"}
ALLOWED_RESEARCH_STATUSES = {"pending", "available", "blocked"}
ALLOWED_RISK_FAMILIES = {
    "broad_beta",
    "growth_technology",
    "value_income",
    "consumer",
    "healthcare",
    "industrial_materials",
    "transport_infrastructure",
    "resource_cycle",
    "agriculture_breeding",
}
FORBIDDEN_OFFICIAL_CODES = {"H00015", "931688CNY010", "H20590", "931743CNY010"}
FORBIDDEN_NAME_PARTS = {"算力", "机器人", "半导体材料设备", "量子", "低空经济", "元宇宙"}
ASSET_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


class ResearchUniverseError(ValueError):
    pass


@dataclass(frozen=True)
class ResearchAsset:
    asset_key: str
    official_code: str
    provider_code: str | None
    display_name: str
    tier: str
    research_order: int
    asset_group: str
    risk_family: str
    return_basis: str
    data_source: str
    verification_status: str
    research_status: str
    substitution_allowed: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ResearchUniverse:
    schema_version: str
    universe_id: str
    human_reference: str
    allowed_tiers: tuple[str, ...]
    required_return_basis: str
    required_data_source: str
    assets: tuple[ResearchAsset, ...]
    universe_hash: str

    def require_allowed_asset(self, asset_key: str) -> ResearchAsset:
        for asset in self.assets:
            if asset.asset_key == asset_key:
                return asset
        raise ResearchUniverseError(f"asset_key is not in research universe: {asset_key}")

    def require_allowed_provider_code(self, provider_code: str) -> ResearchAsset:
        for asset in self.assets:
            if asset.provider_code == provider_code:
                return asset
        raise ResearchUniverseError(
            f"provider_code is not in research universe: {provider_code}"
        )

    def assets_for_tier(self, tier: str) -> tuple[ResearchAsset, ...]:
        if tier not in EXPECTED_TIER_COUNTS:
            raise ResearchUniverseError(f"unsupported research tier: {tier}")
        return tuple(asset for asset in self.assets if asset.tier == tier)


def load_research_universe(path: Path) -> ResearchUniverse:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchUniverseError(f"cannot read research universe: {path}") from exc
    validate_research_universe(raw)
    assets = tuple(_parse_asset(value) for value in raw["assets"])
    return ResearchUniverse(
        schema_version=raw["schema_version"],
        universe_id=raw["universe_id"],
        human_reference=raw["human_reference"],
        allowed_tiers=tuple(raw["allowed_tiers"]),
        required_return_basis=raw["required_return_basis"],
        required_data_source=raw["required_data_source"],
        assets=assets,
        universe_hash=canonical_universe_hash(raw),
    )


def validate_research_universe(raw: dict[str, Any]) -> None:
    required_top = {
        "schema_version",
        "universe_id",
        "human_reference",
        "allowed_tiers",
        "required_return_basis",
        "required_data_source",
        "assets",
    }
    if not isinstance(raw, dict) or not required_top.issubset(raw):
        raise ResearchUniverseError("research universe is missing required fields")
    if raw["schema_version"] != "1.0":
        raise ResearchUniverseError("unsupported research universe schema")
    if raw["allowed_tiers"] != ["A", "B", "C"]:
        raise ResearchUniverseError("allowed_tiers must be A, B, C in order")
    if raw["required_return_basis"] != "total_return":
        raise ResearchUniverseError("required return basis must be total_return")
    if raw["required_data_source"] != "tushare":
        raise ResearchUniverseError("required data source must be tushare")
    assets = raw["assets"]
    if not isinstance(assets, list) or len(assets) != 32:
        raise ResearchUniverseError("research universe must contain exactly 32 assets")

    asset_keys: set[str] = set()
    provider_codes: set[str] = set()
    official_codes: set[str] = set()
    tier_counts = {tier: 0 for tier in EXPECTED_TIER_COUNTS}
    orders: list[int] = []
    for value in assets:
        _validate_asset(value)
        asset_key = value["asset_key"]
        provider_code = value["provider_code"]
        official_code = value["official_code"]
        if asset_key in asset_keys:
            raise ResearchUniverseError(f"duplicate asset_key: {asset_key}")
        if provider_code is not None and provider_code in provider_codes:
            raise ResearchUniverseError(f"duplicate provider_code: {provider_code}")
        if official_code in official_codes:
            raise ResearchUniverseError(f"duplicate official_code: {official_code}")
        asset_keys.add(asset_key)
        official_codes.add(official_code)
        if provider_code is not None:
            provider_codes.add(provider_code)
        tier_counts[value["tier"]] += 1
        orders.append(value["research_order"])
    if tier_counts != EXPECTED_TIER_COUNTS:
        raise ResearchUniverseError(
            f"tier counts must be {_expected_tier_counts_text()}"
        )
    if orders != list(range(1, 33)):
        raise ResearchUniverseError("research_order must be the ordered range 1..32")


def canonical_universe_hash(raw: dict[str, Any]) -> str:
    payload = json.dumps(
        raw,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_asset(value: dict[str, Any]) -> None:
    required = {
        "asset_key",
        "official_code",
        "provider_code",
        "display_name",
        "tier",
        "research_order",
        "asset_group",
        "risk_family",
        "return_basis",
        "data_source",
        "verification_status",
        "research_status",
        "substitution_allowed",
        "notes",
    }
    if not isinstance(value, dict) or not required.issubset(value):
        raise ResearchUniverseError("asset is missing required fields")
    if not ASSET_KEY_PATTERN.fullmatch(value["asset_key"]):
        raise ResearchUniverseError(f"invalid asset_key: {value['asset_key']}")
    if not isinstance(value["official_code"], str) or not value["official_code"]:
        raise ResearchUniverseError("official_code must be non-empty")
    if value["provider_code"] is not None and (
        not isinstance(value["provider_code"], str) or not value["provider_code"]
    ):
        raise ResearchUniverseError("provider_code must be non-empty or null")
    if not isinstance(value["display_name"], str) or not value["display_name"]:
        raise ResearchUniverseError("display_name must be non-empty")
    if value["tier"] not in EXPECTED_TIER_COUNTS:
        raise ResearchUniverseError(f"invalid tier: {value['tier']}")
    if not isinstance(value["research_order"], int):
        raise ResearchUniverseError("research_order must be an integer")
    if value["asset_group"] not in ALLOWED_ASSET_GROUPS:
        raise ResearchUniverseError(f"invalid asset_group: {value['asset_group']}")
    if value["risk_family"] not in ALLOWED_RISK_FAMILIES:
        raise ResearchUniverseError(f"invalid risk_family: {value['risk_family']}")
    if value["return_basis"] != "total_return":
        raise ResearchUniverseError("asset return_basis must be total_return")
    if value["data_source"] != "tushare":
        raise ResearchUniverseError("asset data_source must be tushare")
    if value["verification_status"] not in ALLOWED_VERIFICATION_STATUSES:
        raise ResearchUniverseError("invalid verification_status")
    if value["research_status"] not in ALLOWED_RESEARCH_STATUSES:
        raise ResearchUniverseError("invalid research_status")
    if value["substitution_allowed"] is not False:
        raise ResearchUniverseError("asset substitution must be disabled")
    if not isinstance(value["notes"], list) or not all(
        isinstance(note, str) for note in value["notes"]
    ):
        raise ResearchUniverseError("asset notes must be a list of strings")
    if value["official_code"] in FORBIDDEN_OFFICIAL_CODES or any(
        part in value["display_name"] for part in FORBIDDEN_NAME_PARTS
    ):
        raise ResearchUniverseError(
            f"excluded asset cannot enter research universe: {value['display_name']}"
        )
    if value["research_status"] == "available" and (
        value["verification_status"] != "verified" or value["provider_code"] is None
    ):
        raise ResearchUniverseError(
            "available asset requires verified non-null provider_code"
        )
    if value["verification_status"] == "verified" and value["provider_code"] is None:
        raise ResearchUniverseError("verified asset requires non-null provider_code")
    if value["verification_status"] == "unavailable" and (
        value["provider_code"] is not None or value["research_status"] != "blocked"
    ):
        raise ResearchUniverseError(
            "unavailable asset requires null provider_code and blocked research_status"
        )


def _parse_asset(value: dict[str, Any]) -> ResearchAsset:
    return ResearchAsset(
        asset_key=value["asset_key"],
        official_code=value["official_code"],
        provider_code=value["provider_code"],
        display_name=value["display_name"],
        tier=value["tier"],
        research_order=value["research_order"],
        asset_group=value["asset_group"],
        risk_family=value["risk_family"],
        return_basis=value["return_basis"],
        data_source=value["data_source"],
        verification_status=value["verification_status"],
        research_status=value["research_status"],
        substitution_allowed=value["substitution_allowed"],
        notes=tuple(value["notes"]),
    )


def _expected_tier_counts_text() -> str:
    return ", ".join(f"{tier}={count}" for tier, count in EXPECTED_TIER_COUNTS.items())
