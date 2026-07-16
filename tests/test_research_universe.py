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
