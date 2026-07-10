import copy

import pytest

from engine.asset_registry import (
    AssetMapping,
    ExecutionAsset,
    ResearchAsset,
    build_research_universe_audit,
    execution_assets_by_id,
    load_asset_mappings,
    load_asset_registry,
    load_execution_universe,
    load_research_universe,
    mappings_by_research_asset,
    research_assets_by_id,
    validate_execution_assets,
    validate_mappings,
    validate_registry,
    validate_research_assets,
)


RESEARCH_ROW = {
    "asset_id": "H00300.CSI",
    "name": "沪深300收益",
    "instrument_type": "index",
    "role": "research",
    "category": "broad_base",
    "sleeve": "equity_core",
    "provider": "tushare",
    "data_api": "index_daily",
    "return_basis": "total_return",
    "data_start_date": None,
    "investable_start_date": None,
    "eligible_for_allocation": True,
    "notes": "test",
}

EXECUTION_ROW = {
    "asset_id": "510300.SH",
    "name": "沪深300ETF",
    "instrument_type": "etf",
    "role": "execution",
    "provider": "tushare",
    "data_api": "fund_daily",
    "return_basis": "qfq",
    "data_start_date": None,
    "investable_start_date": None,
    "management_fee": None,
    "tracking_error": None,
    "liquidity_score": None,
    "notes": "test",
}

MAPPING_ROW = {
    "research_asset_id": "H00300.CSI",
    "research_asset_name": "沪深300收益",
    "primary_execution_proxy": "510300.SH",
    "execution_proxies": ["510300.SH"],
    "mapping_quality": "high",
    "notes": "test",
}


def test_research_asset_from_mapping_round_trips():
    asset = ResearchAsset.from_mapping(RESEARCH_ROW)

    assert asset.asset_id == "H00300.CSI"
    assert asset.as_dict()["return_basis"] == "total_return"


def test_execution_asset_from_mapping_round_trips():
    asset = ExecutionAsset.from_mapping(EXECUTION_ROW)

    assert asset.asset_id == "510300.SH"
    assert asset.as_dict()["return_basis"] == "qfq"


def test_asset_mapping_from_mapping_round_trips():
    mapping = AssetMapping.from_mapping(MAPPING_ROW)

    assert mapping.primary_execution_proxy == "510300.SH"
    assert mapping.as_dict()["execution_proxies"] == ["510300.SH"]


@pytest.mark.parametrize("field", sorted(ResearchAsset.REQUIRED_FIELDS))
def test_research_asset_missing_required_field_raises(field):
    row = copy.deepcopy(RESEARCH_ROW)
    row.pop(field)

    with pytest.raises(ValueError, match="missing fields"):
        ResearchAsset.from_mapping(row)


@pytest.mark.parametrize("field", sorted(ExecutionAsset.REQUIRED_FIELDS))
def test_execution_asset_missing_required_field_raises(field):
    row = copy.deepcopy(EXECUTION_ROW)
    row.pop(field)

    with pytest.raises(ValueError, match="missing fields"):
        ExecutionAsset.from_mapping(row)


@pytest.mark.parametrize("field", sorted(AssetMapping.REQUIRED_FIELDS))
def test_asset_mapping_missing_required_field_raises(field):
    row = copy.deepcopy(MAPPING_ROW)
    row.pop(field)

    with pytest.raises(ValueError, match="missing fields"):
        AssetMapping.from_mapping(row)


def test_asset_mapping_requires_proxy_list():
    row = copy.deepcopy(MAPPING_ROW)
    row["execution_proxies"] = "510300.SH"

    with pytest.raises(ValueError, match="execution_proxies must be a list"):
        AssetMapping.from_mapping(row)


def test_validate_research_assets_accepts_valid_asset():
    assert validate_research_assets([ResearchAsset.from_mapping(RESEARCH_ROW)]) == []


def test_validate_research_assets_rejects_invalid_return_basis():
    asset = ResearchAsset.from_mapping({**RESEARCH_ROW, "return_basis": "unknown"})

    assert any("invalid return_basis" in error for error in validate_research_assets([asset]))


def test_validate_research_assets_rejects_invalid_data_api():
    asset = ResearchAsset.from_mapping({**RESEARCH_ROW, "data_api": "unknown"})

    assert any("invalid data_api" in error for error in validate_research_assets([asset]))


def test_validate_research_assets_rejects_invalid_role():
    asset = ResearchAsset.from_mapping({**RESEARCH_ROW, "role": "execution"})

    assert any("invalid role" in error for error in validate_research_assets([asset]))


def test_validate_research_assets_requires_bool_allocation_flag():
    asset = ResearchAsset.from_mapping({**RESEARCH_ROW, "eligible_for_allocation": "yes"})

    assert any("must be bool" in error for error in validate_research_assets([asset]))


def test_validate_research_assets_excludes_industry_monitor():
    asset = ResearchAsset.from_mapping(
        {
            **RESEARCH_ROW,
            "asset_id": "801780.SI",
            "name": "银行",
            "instrument_type": "sw_index",
            "role": "monitor",
            "category": "industry",
            "sleeve": "industry_monitor",
            "data_api": "sw_daily",
            "return_basis": "price_index",
            "eligible_for_allocation": True,
        }
    )

    errors = validate_research_assets([asset])

    assert any("industry monitor" in error for error in errors)
    assert any("price_index cannot be eligible" in error for error in errors)


def test_validate_research_assets_rejects_price_index_allocation():
    asset = ResearchAsset.from_mapping(
        {**RESEARCH_ROW, "asset_id": "P", "return_basis": "price_index", "eligible_for_allocation": True}
    )

    assert any("price_index cannot be eligible" in error for error in validate_research_assets([asset]))


def test_validate_execution_assets_accepts_valid_asset():
    assert validate_execution_assets([ExecutionAsset.from_mapping(EXECUTION_ROW)]) == []


def test_validate_execution_assets_rejects_invalid_role():
    asset = ExecutionAsset.from_mapping({**EXECUTION_ROW, "role": "research"})

    assert any("invalid role" in error for error in validate_execution_assets([asset]))


def test_validate_execution_assets_rejects_invalid_return_basis():
    asset = ExecutionAsset.from_mapping({**EXECUTION_ROW, "return_basis": "total_return_candidate"})

    assert any("invalid return_basis" in error for error in validate_execution_assets([asset]))


def test_validate_mappings_accepts_valid_mapping():
    assert validate_mappings(
        [AssetMapping.from_mapping(MAPPING_ROW)],
        [ResearchAsset.from_mapping(RESEARCH_ROW)],
        [ExecutionAsset.from_mapping(EXECUTION_ROW)],
    ) == []


def test_validate_mappings_rejects_unknown_research_asset():
    mapping = AssetMapping.from_mapping({**MAPPING_ROW, "research_asset_id": "UNKNOWN"})

    assert any(
        "unknown research asset" in error
        for error in validate_mappings([mapping], [ResearchAsset.from_mapping(RESEARCH_ROW)], [ExecutionAsset.from_mapping(EXECUTION_ROW)])
    )


def test_validate_mappings_rejects_unknown_execution_proxy():
    mapping = AssetMapping.from_mapping({**MAPPING_ROW, "execution_proxies": ["UNKNOWN"], "primary_execution_proxy": "UNKNOWN"})

    assert any(
        "unknown execution proxy" in error
        for error in validate_mappings([mapping], [ResearchAsset.from_mapping(RESEARCH_ROW)], [ExecutionAsset.from_mapping(EXECUTION_ROW)])
    )


def test_validate_mappings_rejects_primary_not_in_proxy_list():
    mapping = AssetMapping.from_mapping({**MAPPING_ROW, "primary_execution_proxy": "510300.SH", "execution_proxies": []})

    assert any(
        "primary proxy" in error
        for error in validate_mappings([mapping], [ResearchAsset.from_mapping(RESEARCH_ROW)], [ExecutionAsset.from_mapping(EXECUTION_ROW)])
    )


def test_validate_mappings_rejects_invalid_quality():
    mapping = AssetMapping.from_mapping({**MAPPING_ROW, "mapping_quality": "great"})

    assert any(
        "invalid mapping_quality" in error
        for error in validate_mappings([mapping], [ResearchAsset.from_mapping(RESEARCH_ROW)], [ExecutionAsset.from_mapping(EXECUTION_ROW)])
    )


def test_validate_mappings_rejects_none_quality_with_primary_proxy():
    mapping = AssetMapping.from_mapping({**MAPPING_ROW, "mapping_quality": "none", "execution_proxies": []})

    assert any(
        "must not have primary proxy" in error
        for error in validate_mappings([mapping], [ResearchAsset.from_mapping(RESEARCH_ROW)], [ExecutionAsset.from_mapping(EXECUTION_ROW)])
    )


def test_validate_mappings_rejects_none_quality_with_proxies():
    mapping = AssetMapping.from_mapping(
        {**MAPPING_ROW, "mapping_quality": "none", "primary_execution_proxy": None, "execution_proxies": ["510300.SH"]}
    )

    assert any(
        "must not have proxies" in error
        for error in validate_mappings([mapping], [ResearchAsset.from_mapping(RESEARCH_ROW)], [ExecutionAsset.from_mapping(EXECUTION_ROW)])
    )


def test_validate_registry_accepts_fixture_registry():
    errors = validate_registry(
        [ResearchAsset.from_mapping(RESEARCH_ROW)],
        [ExecutionAsset.from_mapping(EXECUTION_ROW)],
        [AssetMapping.from_mapping(MAPPING_ROW)],
    )

    assert errors == []


def test_load_research_universe_contains_user_assets():
    ids = {asset.asset_id for asset in load_research_universe()}

    assert {"H00300.CSI", "H20771.CSI", "801780.SI"} <= ids


def test_load_execution_universe_contains_core_proxies():
    ids = {asset.asset_id for asset in load_execution_universe()}

    assert {"510300.SH", "512760.SH", "511010.SH"} <= ids


def test_load_asset_mappings_contains_none_quality_rows():
    mappings = load_asset_mappings()

    assert any(mapping.mapping_quality == "none" for mapping in mappings)


def test_load_asset_registry_returns_all_sections():
    registry = load_asset_registry()

    assert {"research_assets", "execution_assets", "mappings"} <= set(registry)


def test_research_assets_by_id_returns_lookup():
    lookup = research_assets_by_id()

    assert lookup["H00300.CSI"].name == "沪深300收益"


def test_execution_assets_by_id_returns_lookup():
    lookup = execution_assets_by_id()

    assert lookup["510300.SH"].name == "沪深300ETF"


def test_mappings_by_research_asset_returns_lookup():
    lookup = mappings_by_research_asset()

    assert lookup["H00300.CSI"].primary_execution_proxy == "510300.SH"


def test_research_asset_ids_are_unique():
    ids = [asset.asset_id for asset in load_research_universe()]

    assert len(ids) == len(set(ids))


def test_execution_asset_ids_are_unique():
    ids = [asset.asset_id for asset in load_execution_universe()]

    assert len(ids) == len(set(ids))


def test_mapping_research_asset_ids_are_unique():
    ids = [mapping.research_asset_id for mapping in load_asset_mappings()]

    assert len(ids) == len(set(ids))


def test_industry_assets_are_monitor_only():
    industry_assets = [asset for asset in load_research_universe() if asset.category == "industry"]

    assert len(industry_assets) == 18
    assert all(asset.role == "monitor" for asset in industry_assets)
    assert all(asset.eligible_for_allocation is False for asset in industry_assets)


def test_total_return_assets_remain_allocation_eligible():
    total_return_assets = [asset for asset in load_research_universe() if asset.return_basis == "total_return"]

    assert len(total_return_assets) == 14
    assert all(asset.eligible_for_allocation for asset in total_return_assets)


def test_audit_counts_registry_sections():
    audit = build_research_universe_audit()

    assert audit["research_asset_count"] == 32
    assert audit["execution_asset_count"] == 13
    assert audit["mapping_count"] == 32


def test_audit_counts_return_basis():
    audit = build_research_universe_audit()

    assert audit["return_basis_counts"] == {"price_index": 18, "total_return": 14}


def test_audit_counts_data_apis():
    audit = build_research_universe_audit()

    assert audit["data_api_counts"]["index_daily"] == 14
    assert audit["data_api_counts"]["sw_daily"] == 18
    assert audit["data_api_counts"]["fund_daily"] == 13


def test_audit_counts_mapping_quality():
    audit = build_research_universe_audit()

    assert audit["mapping_quality_counts"]["none"] == 22
    assert audit["mapping_quality_counts"]["low"] == 1


def test_audit_warns_on_price_index_assets():
    audit = build_research_universe_audit()

    assert any("801780.SI 银行 uses price_index" in warning for warning in audit["warnings"])


def test_audit_warns_on_missing_execution_proxy():
    audit = build_research_universe_audit()

    assert any("H21152.CSI has no execution proxy" in warning for warning in audit["warnings"])


def test_audit_has_no_errors_for_checked_in_registry():
    audit = build_research_universe_audit()

    assert audit["errors"] == []
