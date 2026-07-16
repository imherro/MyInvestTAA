from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_strategy_style_category_states.py"
SPEC = importlib.util.spec_from_file_location("strategy_style_category_states", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture(scope="session")
def artifact_bytes() -> dict[str, bytes]:
    return MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF)


@pytest.fixture(scope="session")
def decoded(artifact_bytes: dict[str, bytes]) -> dict[str, Any]:
    return {name: json.loads(content) for name, content in artifact_bytes.items()}


def _copy_formal_inputs(target: Path) -> None:
    relatives = [
        MODULE.UNIVERSE_RELATIVE,
        MODULE.DATASET_MANIFEST_RELATIVE,
        MODULE.CALENDAR_RELATIVE,
        MODULE.QUALIFICATION_RELATIVE,
        *MODULE.CONTRACT_RELATIVES,
    ]
    manifest = json.loads((ROOT / MODULE.DATASET_MANIFEST_RELATIVE).read_text(encoding="utf-8"))
    relatives.extend(Path(row["price_file"]) for row in manifest["assets"])
    for relative in relatives:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)


def _rewrite_json(path: Path, mutator: Any) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutator(value)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_formal_inputs_validate_and_wrong_as_of_fails() -> None:
    validated = MODULE.load_and_validate_inputs(ROOT, MODULE.AS_OF)
    assert validated["common_dates"][0] == "2013-01-04"
    assert validated["common_dates"][-1] == MODULE.AS_OF
    assert len(validated["common_dates"]) == 3284
    with pytest.raises(MODULE.StrategyStyleCategoryStateError, match="--as-of"):
        MODULE.load_and_validate_inputs(ROOT, "2026-07-14")


def test_nonqualified_source_fails_closed(tmp_path: Path) -> None:
    _copy_formal_inputs(tmp_path)
    path = tmp_path / MODULE.QUALIFICATION_RELATIVE
    _rewrite_json(path, lambda value: value.update(overall_status="BLOCKED"))
    with pytest.raises(MODULE.StrategyStyleCategoryStateError, match="not QUALIFIED"):
        MODULE.load_and_validate_inputs(tmp_path, MODULE.AS_OF)


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        (MODULE.UNIVERSE_RELATIVE, "universe hash"),
        (MODULE.DATASET_MANIFEST_RELATIVE, "manifest hash"),
        (MODULE.CALENDAR_RELATIVE, "calendar hash"),
        (Path("data/strategy_style_research/prices/CN2296_CNI.json"), "price hash"),
    ],
)
def test_every_source_hash_chain_fails_closed(tmp_path: Path, relative: Path, message: str) -> None:
    _copy_formal_inputs(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b" \n")
    with pytest.raises(MODULE.StrategyStyleCategoryStateError, match=message):
        MODULE.load_and_validate_inputs(tmp_path, MODULE.AS_OF)


def test_builder_is_offline_and_ignores_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "must-not-be-used")
    import socket

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network used")))
    artifacts = MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF)
    assert set(artifacts) == {"manifest.json", "common_panel.json", "category_states.json"}
    source = SCRIPT.read_text(encoding="utf-8")
    assert "TUSHARE_TOKEN" not in source
    assert 'root / ".env"' not in source


def test_common_panel_contract_and_first_rows(decoded: dict[str, Any]) -> None:
    panel = decoded["common_panel.json"]
    assert panel["dataset_id"] == "STRATEGY_STYLE_COMMON_PANEL_V1"
    assert panel["session_count"] == 3284
    assert panel["member_count"] == 5
    assert panel["style_unit_count"] == 4
    assert panel["member_date_observation_count"] == 16420
    assert panel["dates"][0] == "2013-01-04"
    assert panel["dates"][-1] == "2026-07-15"
    assert [member["asset_id"] for member in panel["members"]] == [item[0] for item in MODULE.MEMBER_SPECS]
    for member in panel["members"]:
        assert member["return_basis"] == "total_return"
        assert member["daily_total_return"][0] is None
        assert member["normalized_level"][0] == 1.0
        assert member["cumulative_total_return"][0] == 0.0
        assert member["running_peak_level"][0] == 1.0
        assert member["drawdown"][0] == 0.0
        for key in ("close", "daily_total_return", "normalized_level", "cumulative_total_return", "running_peak_level", "drawdown"):
            assert len(member[key]) == 3284


def test_common_panel_histories_use_exact_formulas(decoded: dict[str, Any]) -> None:
    member = decoded["common_panel.json"]["members"][0]
    for index in (1, 100, 3283):
        assert member["daily_total_return"][index] == pytest.approx(member["close"][index] / member["close"][index - 1] - 1)
        assert member["normalized_level"][index] == pytest.approx(member["close"][index] / member["close"][0])
        assert member["cumulative_total_return"][index] == pytest.approx(member["normalized_level"][index] - 1)
        assert member["running_peak_level"][index] == max(member["normalized_level"][: index + 1])
        assert member["drawdown"][index] == pytest.approx(member["normalized_level"][index] / member["running_peak_level"][index] - 1)


def test_profiles_are_exact_frozen_indivisible_sets(decoded: dict[str, Any]) -> None:
    states = decoded["category_states.json"]
    assert states["profile_order"] == ["PROFILE_A", "PROFILE_B", "PROFILE_C"]
    assert [(row["profile_id"], row["parameters"]) for row in states["profiles"]] == [
        ("PROFILE_A", {"pressure_threshold": 0.10, "absolute_horizon": 10, "relative_horizon": 20, "adverse_lookback": 10}),
        ("PROFILE_B", {"pressure_threshold": 0.15, "absolute_horizon": 20, "relative_horizon": 40, "adverse_lookback": 20}),
        ("PROFILE_C", {"pressure_threshold": 0.20, "absolute_horizon": 40, "relative_horizon": 60, "adverse_lookback": 40}),
    ]


def test_warmup_median_and_prior_min_excludes_current(decoded: dict[str, Any]) -> None:
    panel = decoded["common_panel.json"]
    profile = decoded["category_states.json"]["profiles"][0]
    calculations = {row["asset_id"]: row for row in profile["member_calculations"]}
    for row in calculations.values():
        assert row["absolute_horizon_return"][:10] == [None] * 10
        assert row["relative_horizon_return"][:20] == [None] * 20
        assert row["relative_peer_median_return"][:20] == [None] * 20
        assert row["relative_return_gap"][:20] == [None] * 20
        assert row["states"]["relative_stabilization"][:20] == ["UNAVAILABLE"] * 20
        assert row["adverse_prior_min_level"][:10] == [None] * 10
    index = 20
    own = calculations["CN2296.CNI"]
    peers = sorted(calculations[asset]["relative_horizon_return"][index] for asset in calculations if asset != "CN2296.CNI")
    expected_median = (peers[1] + peers[2]) / 2
    assert own["relative_peer_median_return"][index] == pytest.approx(expected_median)
    member = next(row for row in panel["members"] if row["asset_id"] == "CN2296.CNI")
    assert own["adverse_prior_min_level"][10] == min(member["normalized_level"][:10])


def test_formal_horizon_returns_use_close_exactly(decoded: dict[str, Any]) -> None:
    panel = decoded["common_panel.json"]
    panel_members = {row["asset_id"]: row for row in panel["members"]}
    for profile in decoded["category_states.json"]["profiles"]:
        absolute_horizon = profile["parameters"]["absolute_horizon"]
        relative_horizon = profile["parameters"]["relative_horizon"]
        for calculation in profile["member_calculations"]:
            closes = panel_members[calculation["asset_id"]]["close"]
            index = relative_horizon + 7
            assert calculation["absolute_horizon_return"][index] == closes[index] / closes[index - absolute_horizon] - 1
            assert calculation["relative_horizon_return"][index] == closes[index] / closes[index - relative_horizon] - 1


def test_close_and_normalized_float_paths_are_not_substituted() -> None:
    dates = [f"D{index:02d}" for index in range(22)]
    members = []
    for asset_id, style, display_name in MODULE.MEMBER_SPECS:
        closes = [0.1] + [0.3] * 20 + [1.1]
        closes[11] = 1.1
        levels = [value / closes[0] for value in closes]
        members.append(
            {
                "asset_id": asset_id,
                "style_unit": style,
                "display_name": display_name,
                "close": closes,
                "normalized_level": levels,
                "drawdown": [0.0] * len(dates),
            }
        )
    panel = {"dates": dates, "members": members}
    states = MODULE.build_category_states(panel, "0" * 64)
    calculation = states["profiles"][0]["member_calculations"][0]
    close_absolute = members[0]["close"][11] / members[0]["close"][1] - 1
    normalized_absolute = members[0]["normalized_level"][11] / members[0]["normalized_level"][1] - 1
    close_relative = members[0]["close"][21] / members[0]["close"][1] - 1
    normalized_relative = members[0]["normalized_level"][21] / members[0]["normalized_level"][1] - 1
    assert close_absolute != normalized_absolute
    assert close_relative != normalized_relative
    assert calculation["absolute_horizon_return"][11] == close_absolute
    assert calculation["absolute_horizon_return"][11] != normalized_absolute
    assert calculation["relative_horizon_return"][21] == close_relative
    assert calculation["relative_horizon_return"][21] != normalized_relative


def test_boundary_values_are_frozen() -> None:
    assert MODULE._state(-0.10, lambda value: value <= -0.10) == "MET"
    assert MODULE._state(0.0, lambda value: value >= 0.0) == "MET"
    assert MODULE._prior_minima([1.0, 0.9, 0.9], 2)[2] == 0.9
    states = MODULE._aggregate_dividend(
        [
            {category: ["MET", "NOT_MET", "MET"] for category in MODULE.CATEGORIES},
            {category: ["MET", "MET", "UNAVAILABLE"] for category in MODULE.CATEGORIES},
        ]
    )
    aggregated, agreement = states
    assert aggregated["drawdown_pressure"] == ["MET", "NOT_MET", "UNAVAILABLE"]
    assert aggregated["adverse_continuation"] == ["MET", "MET", "UNAVAILABLE"]
    assert agreement == ["AGREEMENT", "CONFLICT", "UNAVAILABLE"]


def test_style_order_mapping_aggregation_and_agreement(decoded: dict[str, Any]) -> None:
    for profile in decoded["category_states.json"]["profiles"]:
        calculations = {row["asset_id"]: row for row in profile["member_calculations"]}
        styles = profile["style_states"]
        assert [row["style_unit"] for row in styles] == ["growth", "value", "dividend", "cash_flow"]
        assert [row["member_asset_ids"] for row in styles] == [
            ["CN2296.CNI"], ["CN2371.CNI"], ["H00015.CSI", "H00922.CSI"], ["480092.CNI"]
        ]
        assert styles[0]["states"] == calculations["CN2296.CNI"]["states"]
        assert styles[1]["states"] == calculations["CN2371.CNI"]["states"]
        assert styles[3]["states"] == calculations["480092.CNI"]["states"]
        expected_states, expected_agreement = MODULE._aggregate_dividend(
            [calculations["H00015.CSI"]["states"], calculations["H00922.CSI"]["states"]]
        )
        assert styles[2]["states"] == expected_states
        assert styles[2]["dividend_member_agreement"] == expected_agreement


def test_state_arrays_enums_availability_and_no_nonfinite(decoded: dict[str, Any]) -> None:
    states = decoded["category_states.json"]
    panel_dates = decoded["common_panel.json"]["dates"]
    assert states["date_count"] == 3284
    assert states["date_axis"] == "common_panel.dates"
    assert states["common_state_values"] == ["MET", "NOT_MET", "UNAVAILABLE"]
    assert states["agreement_state_values"] == ["AGREEMENT", "CONFLICT", "UNAVAILABLE"]
    for profile in states["profiles"]:
        availability = profile["availability"]
        assert all(value in panel_dates for value in availability.values())
        for member in profile["member_calculations"]:
            for key in ("absolute_horizon_return", "relative_horizon_return", "relative_peer_median_return", "relative_return_gap", "adverse_prior_min_level"):
                assert len(member[key]) == 3284
                assert all(value is None or math.isfinite(value) for value in member[key])
            for values in member["states"].values():
                assert len(values) == 3284
                assert set(values) <= set(states["common_state_values"])
        dividend = profile["style_states"][2]
        assert len(dividend["dividend_member_agreement"]) == 3284
        assert set(dividend["dividend_member_agreement"]) <= set(states["agreement_state_values"])


def test_no_forbidden_downstream_outputs(artifact_bytes: dict[str, bytes]) -> None:
    combined = b"\n".join(artifact_bytes.values()).decode("utf-8")
    forbidden = [
        "ENTRY_CANDIDATE", "HOLD_CANDIDATE", "EXIT_CANDIDATE", "BUY", "SELL",
        "TARGET_WEIGHT", "event_id", "forward_return", "best_profile", "sharpe",
        "calmar", "maximum_drawdown", "position", "transaction_cost",
    ]
    assert not any(term in combined for term in forbidden)


def test_bytes_are_deterministic_and_manifest_hashes_match(artifact_bytes: dict[str, bytes]) -> None:
    second = MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF)
    assert second == artifact_bytes
    manifest = json.loads(artifact_bytes["manifest.json"])
    for key, filename in (("common_panel", "common_panel.json"), ("category_states", "category_states.json")):
        record = manifest["outputs"][key]
        assert record["sha256"] == hashlib.sha256(artifact_bytes[filename]).hexdigest()
        assert record["bytes"] == len(artifact_bytes[filename])


def test_failed_publish_preserves_previous_complete_directory(
    tmp_path: Path, artifact_bytes: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / MODULE.OUTPUT_RELATIVE
    target.mkdir(parents=True)
    (target / "old.json").write_text('{"old":true}\n', encoding="utf-8")
    real_replace = os.replace
    failed = False

    def fail_new_directory(source: Any, destination: Any) -> None:
        nonlocal failed
        if not failed and Path(source).name == "complete" and Path(destination) == target:
            failed = True
            raise OSError("simulated replacement failure")
        real_replace(source, destination)

    monkeypatch.setattr(MODULE.os, "replace", fail_new_directory)
    with pytest.raises(OSError, match="simulated replacement failure"):
        MODULE.publish_artifacts(tmp_path, artifact_bytes)
    assert {path.name for path in target.iterdir()} == {"old.json"}
    assert (target / "old.json").read_text(encoding="utf-8") == '{"old":true}\n'


def test_formal_source_and_output_boundaries() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden_inputs = (
        "research_prices", "reports/current", "CURRENT_TAA", "shadow-portfolio",
        "execution-backtest", "drawdown_addon",
    )
    assert not any(term in source for term in forbidden_inputs)
    output_dir = ROOT / MODULE.OUTPUT_RELATIVE
    if output_dir.exists():
        assert {path.name for path in output_dir.iterdir() if path.is_file()} == {
            "manifest.json", "common_panel.json", "category_states.json"
        }
