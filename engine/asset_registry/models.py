from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _missing_fields(row: dict, required: set[str], label: str) -> None:
    missing = sorted(required - set(row))
    if missing:
        raise ValueError(f"{label} missing fields: {missing}")


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


@dataclass(frozen=True)
class ResearchAsset:
    asset_id: str
    name: str
    instrument_type: str
    role: str
    category: str
    sleeve: str
    provider: str
    data_api: str
    return_basis: str
    data_start_date: str | None
    investable_start_date: str | None
    eligible_for_allocation: bool
    notes: str = ""

    REQUIRED_FIELDS = {
        "asset_id",
        "name",
        "instrument_type",
        "role",
        "category",
        "sleeve",
        "provider",
        "data_api",
        "return_basis",
        "data_start_date",
        "investable_start_date",
        "eligible_for_allocation",
    }

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "ResearchAsset":
        _missing_fields(row, cls.REQUIRED_FIELDS, "research asset")
        return cls(
            asset_id=str(row["asset_id"]),
            name=str(row["name"]),
            instrument_type=str(row["instrument_type"]),
            role=str(row["role"]),
            category=str(row["category"]),
            sleeve=str(row["sleeve"]),
            provider=str(row["provider"]),
            data_api=str(row["data_api"]),
            return_basis=str(row["return_basis"]),
            data_start_date=row["data_start_date"],
            investable_start_date=row["investable_start_date"],
            eligible_for_allocation=row["eligible_for_allocation"],
            notes=str(row.get("notes") or ""),
        )

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "instrument_type": self.instrument_type,
            "role": self.role,
            "category": self.category,
            "sleeve": self.sleeve,
            "provider": self.provider,
            "data_api": self.data_api,
            "return_basis": self.return_basis,
            "data_start_date": self.data_start_date,
            "investable_start_date": self.investable_start_date,
            "eligible_for_allocation": self.eligible_for_allocation,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExecutionAsset:
    asset_id: str
    name: str
    instrument_type: str
    role: str
    provider: str
    data_api: str
    return_basis: str
    data_start_date: str | None
    investable_start_date: str | None
    management_fee: float | None = None
    tracking_error: float | None = None
    liquidity_score: float | None = None
    notes: str = ""

    REQUIRED_FIELDS = {
        "asset_id",
        "name",
        "instrument_type",
        "role",
        "provider",
        "data_api",
        "return_basis",
        "data_start_date",
        "investable_start_date",
    }

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "ExecutionAsset":
        _missing_fields(row, cls.REQUIRED_FIELDS, "execution asset")
        return cls(
            asset_id=str(row["asset_id"]),
            name=str(row["name"]),
            instrument_type=str(row["instrument_type"]),
            role=str(row["role"]),
            provider=str(row["provider"]),
            data_api=str(row["data_api"]),
            return_basis=str(row["return_basis"]),
            data_start_date=row["data_start_date"],
            investable_start_date=row["investable_start_date"],
            management_fee=_optional_float(row.get("management_fee")),
            tracking_error=_optional_float(row.get("tracking_error")),
            liquidity_score=_optional_float(row.get("liquidity_score")),
            notes=str(row.get("notes") or ""),
        )

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "instrument_type": self.instrument_type,
            "role": self.role,
            "provider": self.provider,
            "data_api": self.data_api,
            "return_basis": self.return_basis,
            "data_start_date": self.data_start_date,
            "investable_start_date": self.investable_start_date,
            "management_fee": self.management_fee,
            "tracking_error": self.tracking_error,
            "liquidity_score": self.liquidity_score,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class AssetMapping:
    research_asset_id: str
    research_asset_name: str
    primary_execution_proxy: str | None
    execution_proxies: list[str]
    mapping_quality: str
    notes: str = ""

    REQUIRED_FIELDS = {
        "research_asset_id",
        "research_asset_name",
        "primary_execution_proxy",
        "execution_proxies",
        "mapping_quality",
    }

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "AssetMapping":
        _missing_fields(row, cls.REQUIRED_FIELDS, "asset mapping")
        proxies = row["execution_proxies"]
        if not isinstance(proxies, list):
            raise ValueError("asset mapping execution_proxies must be a list")
        primary = row["primary_execution_proxy"]
        return cls(
            research_asset_id=str(row["research_asset_id"]),
            research_asset_name=str(row["research_asset_name"]),
            primary_execution_proxy=None if primary is None else str(primary),
            execution_proxies=[str(item) for item in proxies],
            mapping_quality=str(row["mapping_quality"]),
            notes=str(row.get("notes") or ""),
        )

    def as_dict(self) -> dict:
        return {
            "research_asset_id": self.research_asset_id,
            "research_asset_name": self.research_asset_name,
            "primary_execution_proxy": self.primary_execution_proxy,
            "execution_proxies": list(self.execution_proxies),
            "mapping_quality": self.mapping_quality,
            "notes": self.notes,
        }
