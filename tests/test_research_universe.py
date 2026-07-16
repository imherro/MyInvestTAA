from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from current_taa.research_universe import (
    ResearchUniverseError,
    canonical_universe_hash,
    load_research_universe,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "research_universe_v1.json"
EXPECTED_RISK_FAMILIES = {
    "csi300_total_return": "broad_beta",
    "csi500_total_return": "broad_beta",
    "csi1000_total_return": "broad_beta",
    "chinext_total_return": "growth_technology",
    "cni1000_value_total_return": "value_income",
    "csi_dividend_total_return": "value_income",
    "cni_free_cash_flow_total_return": "value_income",
    "cni_food_beverage_total_return": "consumer",
    "cni_durable_consumer_total_return": "consumer",
    "cni_consumer_services_total_return": "consumer",
    "cni_healthcare_total_return": "healthcare",
    "cni_utilities_total_return": "value_income",
    "cni_banks_total_return": "value_income",
    "cni_basic_chemicals_total_return": "industrial_materials",
    "cni_transportation_total_return": "transport_infrastructure",
    "cni_nonferrous_metals_total_return": "resource_cycle",
    "cni_information_technology_total_return": "growth_technology",
    "cni_communications_total_return": "growth_technology",
    "cni_semiconductor_chip_total_return": "growth_technology",
    "star50_total_return": "growth_technology",
    "cni_new_energy_total_return": "growth_technology",
    "csi_innovative_drug_total_return": "healthcare",
    "cni_aerospace_defense_total_return": "growth_technology",
    "cni_transport_infrastructure_total_return": "transport_infrastructure",
    "cni_logistics_total_return": "transport_infrastructure",
    "cni_oil_gas_total_return": "resource_cycle",
    "cni_green_coal_total_return": "resource_cycle",
    "cni_industrial_metals_total_return": "resource_cycle",
    "cni_steel_total_return": "resource_cycle",
    "cni_building_materials_total_return": "industrial_materials",
    "szse_agriculture_total_return": "agriculture_breeding",
    "cni_hog_industry_total_return": "agriculture_breeding",
}


def test_real_contract_has_exact_approved_counts_and_order() -> None:
    universe = load_research_universe(CONTRACT)

    assert len(universe.assets) == 32
    assert [len(universe.assets_for_tier(tier)) for tier in ("A", "B", "C")] == [
        7,
        12,
        13,
    ]
    assert [asset.research_order for asset in universe.assets] == list(range(1, 33))
    assert "H00015" not in {asset.official_code for asset in universe.assets}
    assert "931688CNY010" not in {asset.official_code for asset in universe.assets}
    assert "H20590" not in {asset.official_code for asset in universe.assets}
    assert "931743CNY010" not in {asset.official_code for asset in universe.assets}


def test_real_contract_has_exact_risk_family_mapping() -> None:
    universe = load_research_universe(CONTRACT)

    assert {asset.asset_key: asset.risk_family for asset in universe.assets} == (
        EXPECTED_RISK_FAMILIES
    )
    assert (
        universe.require_allowed_asset("cni_building_materials_total_return").risk_family
        == "industrial_materials"
    )


def test_allowlist_queries_reject_unknown_values() -> None:
    universe = load_research_universe(CONTRACT)

    assert universe.require_allowed_asset("csi300_total_return").official_code == "H00300"
    assert universe.require_allowed_provider_code("H00300.CSI").asset_key == (
        "csi300_total_return"
    )
    with pytest.raises(ResearchUniverseError, match="not in research universe"):
        universe.require_allowed_asset("ai_compute_total_return")
    with pytest.raises(ResearchUniverseError, match="not in research universe"):
        universe.require_allowed_provider_code("931688CNY010.CSI")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda raw: raw["assets"].__setitem__(1, copy.deepcopy(raw["assets"][0])), "duplicate asset_key"),
        (
            lambda raw: raw["assets"][1].__setitem__(
                "provider_code", raw["assets"][0]["provider_code"]
            ),
            "duplicate provider_code",
        ),
        (lambda raw: raw["assets"][0].__setitem__("return_basis", "price"), "total_return"),
        (lambda raw: raw["assets"][0].__setitem__("data_source", "other"), "tushare"),
        (lambda raw: raw["assets"][0].__setitem__("substitution_allowed", True), "disabled"),
        (
            lambda raw: raw["assets"][3].__setitem__("research_status", "available"),
            "verified non-null",
        ),
        (
            lambda raw: raw["assets"][0].__setitem__("risk_family", "unknown_family"),
            "invalid risk_family",
        ),
        (
            lambda raw: raw["assets"][0].__setitem__("risk_family", "Broad_Beta"),
            "invalid risk_family",
        ),
        (
            lambda raw: raw["assets"][4].update(
                verification_status="verified", provider_code=None
            ),
            "verified asset requires non-null",
        ),
        (
            lambda raw: raw["assets"][4].update(
                verification_status="unavailable", provider_code="CN2371.CNI"
            ),
            "unavailable asset requires null",
        ),
        (
            lambda raw: raw["assets"][4].update(
                verification_status="unavailable", research_status="pending"
            ),
            "unavailable asset requires null",
        ),
    ],
)
def test_contract_rejects_invalid_semantics(tmp_path: Path, mutation, message: str) -> None:
    raw = _raw_contract()
    mutation(raw)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ResearchUniverseError, match=message):
        load_research_universe(path)


def test_contract_rejects_excluded_theme(tmp_path: Path) -> None:
    raw = _raw_contract()
    raw["assets"][0]["display_name"] = "AI算力全收益指数"
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ResearchUniverseError, match="excluded asset"):
        load_research_universe(path)


def test_universe_hash_ignores_formatting_but_not_values_or_asset_order() -> None:
    raw = _raw_contract()
    reformatted = json.loads(json.dumps(raw, ensure_ascii=False, indent=8))
    changed = copy.deepcopy(raw)
    changed["assets"][0]["notes"].append("changed")
    reordered = copy.deepcopy(raw)
    reordered["assets"][0], reordered["assets"][1] = (
        reordered["assets"][1],
        reordered["assets"][0],
    )

    assert canonical_universe_hash(raw) == canonical_universe_hash(reformatted)
    assert canonical_universe_hash(raw) != canonical_universe_hash(changed)
    assert canonical_universe_hash(raw) != canonical_universe_hash(reordered)


def _raw_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))
