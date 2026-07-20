from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_strategy_style_walk_forward.py"
SPEC = importlib.util.spec_from_file_location("strategy_style_walk_forward", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _copy_inputs(target: Path) -> None:
    for relative in MODULE.EXPECTED_IDENTITIES:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)


@pytest.fixture(scope="session")
def artifact_bytes() -> dict[str, bytes]:
    return MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF)


@pytest.fixture(scope="session")
def decoded(artifact_bytes: dict[str, bytes]) -> dict[str, Any]:
    return {name: json.loads(content) for name, content in artifact_bytes.items()}


@pytest.fixture(scope="session")
def formal_events() -> dict[str, Any]:
    return json.loads((ROOT / MODULE.EVENTS).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def formal_panel() -> dict[str, Any]:
    return json.loads((ROOT / MODULE.COMMON_PANEL).read_text(encoding="utf-8"))


def test_formal_source_chain_and_wrong_as_of() -> None:
    validated = MODULE.load_and_validate_inputs(ROOT, MODULE.AS_OF)
    assert len(validated["events"]) == 1122
    assert len(validated["dates"]) == 3284
    assert validated["dates"][0] == "2013-01-04"
    assert validated["dates"][-1] == MODULE.AS_OF
    assert list(validated["close_by_member"]) == list(MODULE.MEMBER_ORDER)
    with pytest.raises(MODULE.StrategyStyleWalkForwardError, match="--as-of"):
        MODULE.load_and_validate_inputs(ROOT, "2026-07-14")


@pytest.mark.parametrize("relative", list(MODULE.EXPECTED_IDENTITIES))
def test_each_tampered_formal_input_fails(tmp_path: Path, relative: Path) -> None:
    _copy_inputs(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b" \n")
    with pytest.raises(MODULE.StrategyStyleWalkForwardError, match="formal hash"):
        MODULE.load_and_validate_inputs(tmp_path, MODULE.AS_OF)


def test_event_manifest_status_and_invariant_errors_fail() -> None:
    manifest = json.loads((ROOT / MODULE.EVENT_MANIFEST).read_text(encoding="utf-8"))
    contents = {
        relative: (ROOT / relative).read_bytes()
        for relative in MODULE.EXPECTED_IDENTITIES
    }
    wrong_status = copy.deepcopy(manifest)
    wrong_status["statuses"]["event_dataset_status"] = "NOT_BUILT"
    with pytest.raises(MODULE.StrategyStyleWalkForwardError, match="status mismatch"):
        MODULE._validate_event_manifest(wrong_status, contents)
    wrong_invariant = copy.deepcopy(manifest)
    wrong_invariant["invariants"]["event_count"] = 0
    with pytest.raises(MODULE.StrategyStyleWalkForwardError, match="invariant mismatch"):
        MODULE._validate_event_manifest(wrong_invariant, contents)


def test_builder_is_offline_and_does_not_read_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "must-not-be-used")
    import socket

    monkeypatch.setattr(
        socket,
        "socket",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network used")),
    )
    assert set(MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF)) == {
        "manifest.json",
        "event_outcomes.json",
        "walk_forward_summary.json",
    }
    source = SCRIPT.read_text(encoding="utf-8")
    assert "TUSHARE_TOKEN" not in source
    assert 'root / ".env"' not in source


def test_input_and_output_path_boundaries_are_closed() -> None:
    assert set(MODULE.EXPECTED_IDENTITIES) == {
        MODULE.EVENT_MANIFEST,
        MODULE.EVENTS,
        MODULE.COMMON_PANEL,
        MODULE.OUTCOME_CONTRACT,
        MODULE.EVENT_CONTRACT,
        MODULE.STATE_MACHINE_CONTRACT,
    }
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden_paths = (
        "category_states.json",
        "strategy_style_daily_logic_v1/daily_logic.json",
        "strategy_style_research/prices",
        "data/research_prices",
        "reports/current",
        "reports/strategy_research",
        "current_taa/",
        "shadow-portfolio",
        "execution-backtest",
    )
    assert not any(path in source for path in forbidden_paths)


def test_common_panel_close_arrays_are_total_return_finite_and_positive(
    formal_panel: dict[str, Any],
) -> None:
    assert [row["asset_id"] for row in formal_panel["members"]] == list(
        MODULE.MEMBER_ORDER
    )
    for row in formal_panel["members"]:
        assert row["return_basis"] == "total_return"
        assert len(row["close"]) == MODULE.DATE_COUNT
        assert all(value > 0 for value in row["close"])


def test_style_and_peer_return_formulas_use_raw_close() -> None:
    closes = {
        "CN2296.CNI": [100.0, 100.0, 110.0],
        "CN2371.CNI": [100.0, 100.0, 120.0],
        "H00015.CSI": [100.0, 100.0, 130.0],
        "H00922.CSI": [100.0, 100.0, 150.0],
        "480092.CNI": [100.0, 100.0, 160.0],
    }
    result = MODULE._available_period(
        "growth", 1, 2, ["D0", "D1", "D2"], closes
    )
    assert result["evaluation_end_index"] == 2
    assert result["member_total_returns"] == pytest.approx({"CN2296.CNI": 0.1})
    assert result["style_total_return"] == pytest.approx(0.1)
    assert result["peer_style_total_returns"] == pytest.approx(
        {"value": 0.2, "dividend": 0.4, "cash_flow": 0.6}
    )
    assert result["peer_benchmark_total_return"] == pytest.approx(0.4)
    assert result["peer_relative_return"] == pytest.approx(-0.3)


@pytest.mark.parametrize("status", ["UNAVAILABLE_AS_OF", "NOT_CLOSED"])
def test_unavailable_periods_have_complete_null_structure(status: str) -> None:
    period = MODULE._null_period(status)
    assert set(period) == MODULE.PERIOD_FIELDS
    assert period["availability_status"] == status
    assert all(value is None for key, value in period.items() if key != "availability_status")


def test_formal_outcomes_preserve_event_order_and_closed_fields(
    decoded: dict[str, Any], formal_events: dict[str, Any]
) -> None:
    dataset = decoded["event_outcomes.json"]
    outcomes = dataset["outcomes"]
    assert dataset["event_count"] == len(outcomes) == 1122
    assert [row["event_id"] for row in outcomes] == [
        row["event_id"] for row in formal_events["events"]
    ]
    assert all(set(row) == MODULE.OUTCOME_FIELDS for row in outcomes)
    assert all(
        set(row[key]) == MODULE.PERIOD_FIELDS
        for row in outcomes
        for key in (*MODULE.HORIZON_ORDER, "episode")
    )


def test_formal_result_start_horizons_and_sample_end(
    decoded: dict[str, Any], formal_events: dict[str, Any]
) -> None:
    outcomes = decoded["event_outcomes.json"]["outcomes"]
    dates = json.loads((ROOT / MODULE.COMMON_PANEL).read_text(encoding="utf-8"))[
        "dates"
    ]
    for event, outcome in zip(formal_events["events"], outcomes, strict=True):
        start = event["event_start_index"] + 1
        assert outcome["evaluation_start_index"] == start
        assert outcome["evaluation_start_date"] == (
            dates[start] if start < MODULE.DATE_COUNT else None
        )
        for horizon in MODULE.HORIZON_ORDER:
            period = outcome[horizon]
            end = start + MODULE.HORIZON_LENGTHS[horizon]
            if start < MODULE.DATE_COUNT and end < MODULE.DATE_COUNT:
                assert period["availability_status"] == "AVAILABLE"
                assert period["evaluation_end_index"] == end
                assert period["evaluation_end_date"] == dates[end]
            else:
                assert period == MODULE._null_period("UNAVAILABLE_AS_OF")


def test_synthetic_sample_end_event_has_null_start_date_and_unavailable_horizons() -> None:
    validated = MODULE.load_and_validate_inputs(ROOT, MODULE.AS_OF)
    validated["events"] = [
        {
            "event_id": "PROFILE_A__growth__9999",
            "profile_id": "PROFILE_A",
            "style_unit": "growth",
            "event_status": "OPEN",
            "event_start_index": 3283,
            "event_start_observation_date": MODULE.AS_OF,
        }
    ]
    outcome = MODULE.build_event_outcomes(validated)["outcomes"][0]
    assert outcome["evaluation_start_index"] == 3284
    assert outcome["evaluation_start_date"] is None
    assert all(
        outcome[horizon] == MODULE._null_period("UNAVAILABLE_AS_OF")
        for horizon in MODULE.HORIZON_ORDER
    )
    assert outcome["episode"] == MODULE._null_period("NOT_CLOSED")


def test_formal_episode_uses_exit_plus_one_and_open_is_not_closed(
    decoded: dict[str, Any], formal_events: dict[str, Any]
) -> None:
    outcomes = decoded["event_outcomes.json"]["outcomes"]
    event_by_id = {row["event_id"]: row for row in formal_events["events"]}
    for outcome in outcomes:
        event = event_by_id[outcome["event_id"]]
        episode = outcome["episode"]
        if event["event_status"] == "OPEN":
            assert episode == MODULE._null_period("NOT_CLOSED")
        else:
            start = event["event_start_index"] + 1
            end = event["event_end_index"] + 1
            if start < MODULE.DATE_COUNT and end < MODULE.DATE_COUNT and start < end:
                assert episode["availability_status"] == "AVAILABLE"
                assert episode["evaluation_end_index"] == end
            else:
                assert episode == MODULE._null_period("UNAVAILABLE_AS_OF")


def test_formal_partitions_and_fold_mapping(decoded: dict[str, Any]) -> None:
    outcomes = decoded["event_outcomes.json"]["outcomes"]
    assert set(row["walk_forward_partition"] for row in outcomes) <= set(
        MODULE.PARTITION_VALUES
    )
    for row in outcomes:
        year = int(row["event_start_observation_date"][:4])
        if year <= 2017:
            assert row["walk_forward_partition"] == "DEVELOPMENT_EXCLUDED"
            assert row["walk_forward_fold_id"] is None
        elif year <= 2025:
            assert row["walk_forward_partition"] == "FORMAL_OOS"
            assert row["walk_forward_fold_id"] == f"WF_{year}"
        else:
            assert row["walk_forward_partition"] == "PROSPECTIVE_NOT_SCORED"
            assert row["walk_forward_fold_id"] is None
    assert {row["walk_forward_fold_id"] for row in outcomes if row["walk_forward_partition"] == "FORMAL_OOS"} == set(
        MODULE.FORMAL_FOLD_ORDER
    )


def test_summary_layer_counts_fields_and_empty_semantics(decoded: dict[str, Any]) -> None:
    summary = decoded["walk_forward_summary.json"]
    first = summary["profile_style_fold_horizon"]
    second = summary["profile_style_horizon"]
    third = summary["profile_fold_horizon"]
    fourth = summary["profile_horizon"]
    assert (len(first), len(second), len(third), len(fourth)) == (288, 36, 72, 9)
    assert len(summary["episode_profile_style"]) == 12
    assert all(row["summary_status"] in MODULE.SUMMARY_STATUS_VALUES for row in first)
    for row in first:
        if row["summary_status"] == "NO_ELIGIBLE_EVENTS":
            assert row["eligible_event_count"] == 0
            assert row["positive_count"] == row["flat_count"] == row["negative_count"] == 0
            assert row["median_style_total_return"] is None
            assert row["median_peer_relative_return"] is None
            assert row["positive_rate"] is None
    for row in third:
        if row["summary_status"] == "NO_ELIGIBLE_EVENTS":
            assert row["available_style_count"] == 0
            assert row["profile_fold_median_peer_relative_return"] is None


def test_fold_and_style_aggregation_are_unweighted_medians(decoded: dict[str, Any]) -> None:
    summary = decoded["walk_forward_summary.json"]
    first = summary["profile_style_fold_horizon"]
    second = summary["profile_style_horizon"]
    third = summary["profile_fold_horizon"]
    fourth = summary["profile_horizon"]
    sample_second = second[0]
    fold_values = [
        row["median_peer_relative_return"]
        for row in first
        if row["profile_id"] == sample_second["profile_id"]
        and row["style_unit"] == sample_second["style_unit"]
        and row["horizon"] == sample_second["horizon"]
        and row["summary_status"] == "AVAILABLE"
    ]
    assert sample_second["median_of_fold_median_peer_relative_return"] == MODULE._median(fold_values)
    sample_third = third[0]
    style_values = [
        row["median_peer_relative_return"]
        for row in first
        if row["profile_id"] == sample_third["profile_id"]
        and row["walk_forward_fold_id"] == sample_third["walk_forward_fold_id"]
        and row["horizon"] == sample_third["horizon"]
        and row["summary_status"] == "AVAILABLE"
    ]
    assert sample_third["profile_fold_median_peer_relative_return"] == MODULE._median(style_values)
    sample_fourth = fourth[0]
    profile_fold_values = [
        row["profile_fold_median_peer_relative_return"]
        for row in third
        if row["profile_id"] == sample_fourth["profile_id"]
        and row["horizon"] == sample_fourth["horizon"]
        and row["summary_status"] == "AVAILABLE"
    ]
    assert sample_fourth["median_of_profile_fold_medians"] == MODULE._median(profile_fold_values)


def test_episode_summary_uses_formal_oos_only(decoded: dict[str, Any]) -> None:
    outcomes = decoded["event_outcomes.json"]["outcomes"]
    summary = decoded["walk_forward_summary.json"]
    for row in summary["episode_profile_style"]:
        matching = [
            outcome
            for outcome in outcomes
            if outcome["profile_id"] == row["profile_id"]
            and outcome["style_unit"] == row["style_unit"]
            and outcome["walk_forward_partition"] == "FORMAL_OOS"
        ]
        assert row["closed_available_episode_count"] == sum(
            outcome["episode"]["availability_status"] == "AVAILABLE"
            for outcome in matching
        )
        assert row["open_count"] == sum(
            outcome["episode"]["availability_status"] == "NOT_CLOSED"
            for outcome in matching
        )


def test_profile_support_conditions_follow_frozen_rules(decoded: dict[str, Any]) -> None:
    summary = decoded["walk_forward_summary.json"]
    fourth = {
        (row["profile_id"], row["horizon"]): row
        for row in summary["profile_horizon"]
    }
    assert len(summary["profile_decisions"]) == 3
    for row in summary["profile_decisions"]:
        profile_id = row["profile_id"]
        assert row["condition_a_passed"] == (row["h60_positive_style_count"] >= 3)
        assert row["condition_b_passed"] == (row["h60_positive_fold_count"] >= 5)
        h60 = fourth[(profile_id, "H60")]
        assert row["condition_c_passed"] == (
            h60["available_fold_count"] >= 5
            and h60["median_of_profile_fold_medians"] is not None
            and h60["median_of_profile_fold_medians"] > 0
        )
        assert row["condition_d_passed"] == (
            row["condition_d_h20_passed"] or row["condition_d_h120_passed"]
        )
        expected_support = (
            "WALK_FORWARD_SUPPORTED"
            if all(
                (
                    row["condition_a_passed"],
                    row["condition_b_passed"],
                    row["condition_c_passed"],
                    row["condition_d_passed"],
                )
            )
            else "NOT_SUPPORTED"
        )
        assert row["profile_support_status"] == expected_support


def _synthetic_decisions(
    folds: tuple[int, int, int] = (5, 5, 5),
    styles: tuple[int, int, int] = (3, 3, 3),
    support: tuple[bool, bool, bool] = (True, True, True),
) -> list[dict[str, Any]]:
    return [
        {
            "profile_id": profile_id,
            "h60_positive_fold_count": folds[index],
            "h60_positive_style_count": styles[index],
            "profile_support_status": "WALK_FORWARD_SUPPORTED" if support[index] else "NOT_SUPPORTED",
        }
        for index, profile_id in enumerate(MODULE.PROFILE_ORDER)
    ]


def _synthetic_fourth(
    h60: tuple[float, float, float] = (0.1, 0.1, 0.1),
    h120: tuple[float | None, float | None, float | None] = (0.1, 0.1, 0.1),
    h120_folds: tuple[int, int, int] = (5, 5, 5),
) -> list[dict[str, Any]]:
    rows = []
    for index, profile_id in enumerate(MODULE.PROFILE_ORDER):
        rows.extend(
            [
                {
                    "profile_id": profile_id,
                    "horizon": "H60",
                    "available_fold_count": 8,
                    "median_of_profile_fold_medians": h60[index],
                },
                {
                    "profile_id": profile_id,
                    "horizon": "H120",
                    "available_fold_count": h120_folds[index],
                    "median_of_profile_fold_medians": h120[index],
                },
            ]
        )
    return rows


def test_selection_rejects_none_and_selects_single_supported_profile() -> None:
    none = _synthetic_decisions(support=(False, False, False))
    assert MODULE.select_profile(none, _synthetic_fourth()) == ([], "REJECTED", None)
    single = _synthetic_decisions(support=(False, True, False))
    assert MODULE.select_profile(single, _synthetic_fourth()) == (
        ["PROFILE_B"],
        "SUPPORTED",
        "PROFILE_B",
    )


@pytest.mark.parametrize(
    ("decisions", "fourth", "winner"),
    [
        (_synthetic_decisions(folds=(6, 5, 4)), _synthetic_fourth(), "PROFILE_A"),
        (_synthetic_decisions(styles=(4, 3, 2)), _synthetic_fourth(), "PROFILE_A"),
        (_synthetic_decisions(), _synthetic_fourth(h60=(0.3, 0.2, 0.1)), "PROFILE_A"),
        (
            _synthetic_decisions(),
            _synthetic_fourth(h120=(0.3, 0.2, None), h120_folds=(5, 5, 4)),
            "PROFILE_A",
        ),
    ],
)
def test_multi_profile_selection_each_level(
    decisions: list[dict[str, Any]],
    fourth: list[dict[str, Any]],
    winner: str,
) -> None:
    supported, mechanism, selected = MODULE.select_profile(decisions, fourth)
    assert supported == list(MODULE.PROFILE_ORDER)
    assert mechanism == "SUPPORTED"
    assert selected == winner


def test_multi_profile_invalid_h120_and_partial_ties_are_ambiguous() -> None:
    invalid = _synthetic_fourth(
        h60=(0.1, 0.1, 0.1),
        h120=(None, None, None),
        h120_folds=(4, 4, 4),
    )
    assert MODULE.select_profile(_synthetic_decisions(), invalid)[1:] == (
        "AMBIGUOUS",
        None,
    )
    partial = _synthetic_decisions(folds=(6, 6, 5))
    tied = _synthetic_fourth(h60=(0.2, 0.2, 0.1), h120=(0.3, 0.3, 0.1))
    assert MODULE.select_profile(partial, tied)[1:] == ("AMBIGUOUS", None)


def test_deterministic_bytes_hashes_and_manifest_summary_decision(
    artifact_bytes: dict[str, bytes], decoded: dict[str, Any]
) -> None:
    assert MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF) == artifact_bytes
    manifest = decoded["manifest.json"]
    summary = decoded["walk_forward_summary.json"]
    for key, name in (
        ("event_outcomes", "event_outcomes.json"),
        ("walk_forward_summary", "walk_forward_summary.json"),
    ):
        assert manifest["outputs"][key]["sha256"] == hashlib.sha256(
            artifact_bytes[name]
        ).hexdigest()
        assert manifest["outputs"][key]["bytes"] == len(artifact_bytes[name])
    assert manifest["mechanism_decision"] == summary["mechanism_decision"]
    assert manifest["selected_profile"] == summary["selected_profile"]


def test_no_nonfinite_or_forbidden_portfolio_fields(
    artifact_bytes: dict[str, bytes]
) -> None:
    text = b"".join(artifact_bytes.values()).decode("utf-8")
    assert "NaN" not in text and "Infinity" not in text
    forbidden = (
        "entry_price",
        "exit_price",
        "execution_date",
        "trade_date",
        "position",
        "weight",
        "capital",
        "transaction_cost",
        "portfolio_return",
        "equity_curve",
        "maximum_drawdown",
        "Sharpe",
        "Calmar",
        "win_rate",
        "success_rate",
        "best_profile",
        "profile_rank",
        "style_rank",
    )
    assert not any(term in text for term in forbidden)


def test_failed_publish_preserves_previous_complete_directory(
    tmp_path: Path,
    artifact_bytes: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / MODULE.OUTPUT_DIR
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


def test_output_directory_is_closed_when_published(artifact_bytes: dict[str, bytes]) -> None:
    output_dir = ROOT / MODULE.OUTPUT_DIR
    if output_dir.exists():
        assert {path.name for path in output_dir.iterdir() if path.is_file()} == set(
            artifact_bytes
        )
        assert {
            path.name: path.read_bytes() for path in output_dir.iterdir() if path.is_file()
        } == artifact_bytes
