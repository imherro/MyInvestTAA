from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_strategy_style_daily_logic.py"
SPEC = importlib.util.spec_from_file_location("strategy_style_daily_logic", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _categories(
    pressure: str = "MET",
    absolute: str = "MET",
    relative: str = "MET",
    adverse: str = "NOT_MET",
) -> dict[str, str]:
    return {
        "drawdown_pressure": pressure,
        "absolute_stabilization": absolute,
        "relative_stabilization": relative,
        "adverse_continuation": adverse,
    }


def _source_style(
    style: str,
    daily: list[dict[str, str]] | None = None,
    agreements: list[str] | None = None,
) -> dict[str, Any]:
    daily = daily or [_categories()]
    padded = daily + [_categories(pressure="UNAVAILABLE")] * (
        MODULE.DATE_COUNT - len(daily)
    )
    result = {
        "style_unit": style,
        "member_asset_ids": MODULE.STYLE_MEMBERS[style],
        "states": {
            category: [row[category] for row in padded]
            for category in MODULE.CATEGORIES
        },
    }
    if style == "dividend":
        agreements = agreements or ["AGREEMENT"] * len(daily)
        result["dividend_member_agreement"] = agreements + [
            "UNAVAILABLE"
        ] * (MODULE.DATE_COUNT - len(agreements))
    return result


def _copy_inputs(target: Path) -> None:
    relatives = [
        MODULE.SOURCE_MANIFEST,
        MODULE.COMMON_PANEL,
        MODULE.CATEGORY_STATES,
        *MODULE.UPSTREAM_CONTRACTS.values(),
    ]
    for relative in relatives:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)


def _rewrite_json(path: Path, mutator: Any) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutator(value)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@pytest.fixture(scope="session")
def artifact_bytes() -> dict[str, bytes]:
    return MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF)


@pytest.fixture(scope="session")
def decoded(artifact_bytes: dict[str, bytes]) -> dict[str, Any]:
    return {name: json.loads(content) for name, content in artifact_bytes.items()}


def test_formal_source_chain_and_wrong_as_of() -> None:
    validated = MODULE.load_and_validate_inputs(ROOT, MODULE.AS_OF)
    assert validated["panel"]["dates"][0] == "2013-01-04"
    assert validated["panel"]["dates"][-1] == MODULE.AS_OF
    assert validated["states"]["date_axis"] == "common_panel.dates"
    with pytest.raises(MODULE.StrategyStyleDailyLogicError, match="--as-of"):
        MODULE.load_and_validate_inputs(ROOT, "2026-07-14")


def test_source_manifest_status_mismatch_fails(tmp_path: Path) -> None:
    _copy_inputs(tmp_path)
    path = tmp_path / MODULE.SOURCE_MANIFEST
    _rewrite_json(
        path,
        lambda value: value["statuses"].update(
            entry_exit_state_machine_status="IMPLEMENTED"
        ),
    )
    with pytest.raises(MODULE.StrategyStyleDailyLogicError, match="source status"):
        MODULE.load_and_validate_inputs(tmp_path, MODULE.AS_OF)


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        (MODULE.COMMON_PANEL, "source output hash"),
        (MODULE.CATEGORY_STATES, "source output hash"),
        (MODULE.STATE_MACHINE_CONTRACT, "contract hash"),
    ],
)
def test_tampered_formal_source_fails(
    tmp_path: Path, relative: Path, message: str
) -> None:
    _copy_inputs(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b" \n")
    with pytest.raises(MODULE.StrategyStyleDailyLogicError, match=message):
        MODULE.load_and_validate_inputs(tmp_path, MODULE.AS_OF)


def test_builder_is_offline_and_does_not_read_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "must-not-be-used")
    import socket

    monkeypatch.setattr(
        socket,
        "socket",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("network used")
        ),
    )
    assert set(MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF)) == {
        "manifest.json",
        "daily_logic.json",
    }
    source = SCRIPT.read_text(encoding="utf-8")
    assert "TUSHARE_TOKEN" not in source
    assert 'root / ".env"' not in source


def test_blocked_preserves_inactive_and_active() -> None:
    unavailable = _categories(absolute="UNAVAILABLE")
    assert MODULE.evaluate_day("growth", "INACTIVE", unavailable) == (
        "BLOCKED",
        "INACTIVE",
    )
    assert MODULE.evaluate_day("growth", "ACTIVE", unavailable) == (
        "BLOCKED",
        "ACTIVE",
    )
    assert MODULE.evaluate_day(
        "dividend", "ACTIVE", _categories(), "UNAVAILABLE"
    ) == ("BLOCKED", "ACTIVE")


def test_growth_requires_both_stabilization_categories() -> None:
    assert MODULE.evaluate_day("growth", "INACTIVE", _categories()) == (
        "ENTRY_CANDIDATE",
        "ACTIVE",
    )
    assert MODULE.evaluate_day(
        "growth", "INACTIVE", _categories(relative="NOT_MET")
    ) == ("NO_CHANGE", "INACTIVE")
    assert MODULE.evaluate_day(
        "growth", "INACTIVE", _categories(absolute="NOT_MET")
    ) == ("NO_CHANGE", "INACTIVE")


@pytest.mark.parametrize("style", ["value", "cash_flow"])
def test_value_and_cash_flow_use_stabilization_or(style: str) -> None:
    assert MODULE.evaluate_day(
        style, "INACTIVE", _categories(relative="NOT_MET")
    ) == ("ENTRY_CANDIDATE", "ACTIVE")
    assert MODULE.evaluate_day(
        style, "INACTIVE", _categories(absolute="NOT_MET")
    ) == ("ENTRY_CANDIDATE", "ACTIVE")
    assert MODULE.evaluate_day(
        style,
        "INACTIVE",
        _categories(absolute="NOT_MET", relative="NOT_MET"),
    ) == ("NO_CHANGE", "INACTIVE")


def test_dividend_agreement_enters_and_conflict_prevents_entry() -> None:
    assert MODULE.evaluate_day(
        "dividend", "INACTIVE", _categories(), "AGREEMENT"
    ) == ("ENTRY_CANDIDATE", "ACTIVE")
    assert MODULE.evaluate_day(
        "dividend", "INACTIVE", _categories(), "CONFLICT"
    ) == ("NO_CHANGE", "INACTIVE")


def test_active_styles_hold_instead_of_reentering() -> None:
    for style in MODULE.STYLE_ORDER:
        agreement = "AGREEMENT" if style == "dividend" else None
        assert MODULE.evaluate_day(style, "ACTIVE", _categories(), agreement) == (
            "HOLD_CANDIDATE",
            "ACTIVE",
        )


@pytest.mark.parametrize(
    "categories",
    [
        _categories(adverse="MET"),
        _categories(pressure="NOT_MET"),
        _categories(absolute="NOT_MET", relative="NOT_MET"),
    ],
)
def test_each_common_exit_rule(categories: dict[str, str]) -> None:
    assert MODULE.evaluate_day("value", "ACTIVE", categories) == (
        "EXIT_CANDIDATE",
        "INACTIVE",
    )
    assert MODULE.evaluate_day("value", "INACTIVE", categories) == (
        "NO_CHANGE",
        "INACTIVE",
    )


def test_dividend_conflict_forces_exit() -> None:
    assert MODULE.evaluate_day(
        "dividend", "ACTIVE", _categories(), "CONFLICT"
    ) == ("EXIT_CANDIDATE", "INACTIVE")


def test_entry_exit_recurrence_blocking_and_reentry() -> None:
    source = _source_style(
        "value",
        [
            _categories(),
            _categories(),
            _categories(adverse="MET"),
            _categories(pressure="UNAVAILABLE"),
            _categories(pressure="MET", absolute="NOT_MET", relative="NOT_MET"),
            _categories(),
        ],
    )
    logic = MODULE.build_style_logic("value", source)
    assert logic["state_before"][:6] == [
        "INACTIVE",
        "ACTIVE",
        "ACTIVE",
        "INACTIVE",
        "INACTIVE",
        "INACTIVE",
    ]
    assert logic["daily_result"][:6] == [
        "ENTRY_CANDIDATE",
        "HOLD_CANDIDATE",
        "EXIT_CANDIDATE",
        "BLOCKED",
        "NO_CHANGE",
        "ENTRY_CANDIDATE",
    ]
    assert logic["state_after"][:6] == [
        "ACTIVE",
        "ACTIVE",
        "INACTIVE",
        "INACTIVE",
        "INACTIVE",
        "ACTIVE",
    ]


def test_same_day_priority_blocks_before_exit_or_entry() -> None:
    blocked_adverse = _categories(absolute="UNAVAILABLE", adverse="MET")
    assert MODULE.evaluate_day("growth", "ACTIVE", blocked_adverse) == (
        "BLOCKED",
        "ACTIVE",
    )
    assert MODULE.evaluate_day("growth", "INACTIVE", blocked_adverse) == (
        "BLOCKED",
        "INACTIVE",
    )


def test_concurrent_entry_set_keeps_all_candidates_in_fixed_order() -> None:
    source_styles = [
        _source_style(style, [_categories()]) for style in MODULE.STYLE_ORDER
    ]
    source_profiles = [
        {"profile_id": profile, "style_states": source_styles}
        for profile in MODULE.PROFILE_ORDER
    ]
    validated = {
        "states": {"profiles": source_profiles},
        "source_files": {
            "common_panel": {"sha256": "1" * 64},
            "category_states": {"sha256": "2" * 64},
        },
        "state_machine_contract": {"sha256": "3" * 64},
    }
    logic = MODULE.build_daily_logic(validated)
    for profile in logic["profiles"]:
        assert profile["concurrent_entry_candidate_set"][0] == list(
            MODULE.STYLE_ORDER
        )
        assert profile["concurrent_entry_candidate_set"][1] == []


def test_formal_output_contract_arrays_and_transitions(decoded: dict[str, Any]) -> None:
    logic = decoded["daily_logic.json"]
    assert logic["date_count"] == 3284
    assert logic["date_axis"] == "common_panel.dates"
    assert logic["profile_order"] == list(MODULE.PROFILE_ORDER)
    assert logic["style_order"] == list(MODULE.STYLE_ORDER)
    assert [row["profile_id"] for row in logic["profiles"]] == list(
        MODULE.PROFILE_ORDER
    )
    allowed = {
        ("INACTIVE", "BLOCKED", "INACTIVE"),
        ("INACTIVE", "NO_CHANGE", "INACTIVE"),
        ("INACTIVE", "ENTRY_CANDIDATE", "ACTIVE"),
        ("ACTIVE", "BLOCKED", "ACTIVE"),
        ("ACTIVE", "HOLD_CANDIDATE", "ACTIVE"),
        ("ACTIVE", "EXIT_CANDIDATE", "INACTIVE"),
    }
    for profile in logic["profiles"]:
        assert len(profile["concurrent_entry_candidate_set"]) == 3284
        assert [row["style_unit"] for row in profile["style_logic"]] == list(
            MODULE.STYLE_ORDER
        )
        for style in profile["style_logic"]:
            before, result, after = (
                style["state_before"],
                style["daily_result"],
                style["state_after"],
            )
            assert len(before) == len(result) == len(after) == 3284
            assert before[0] == "INACTIVE"
            assert set(before) <= set(MODULE.LOGICAL_STATES)
            assert set(after) <= set(MODULE.LOGICAL_STATES)
            assert set(result) <= set(MODULE.DAILY_RESULTS)
            assert all(row in allowed for row in zip(before, result, after))
            assert all(before[index] == after[index - 1] for index in range(1, 3284))


def test_formal_concurrent_sets_exactly_match_all_entries(
    decoded: dict[str, Any]
) -> None:
    for profile in decoded["daily_logic.json"]["profiles"]:
        styles = profile["style_logic"]
        for index, candidates in enumerate(
            profile["concurrent_entry_candidate_set"]
        ):
            assert candidates == [
                row["style_unit"]
                for row in styles
                if row["daily_result"][index] == "ENTRY_CANDIDATE"
            ]


def test_deterministic_bytes_and_manifest_output_hash(
    artifact_bytes: dict[str, bytes]
) -> None:
    assert MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF) == artifact_bytes
    manifest = json.loads(artifact_bytes["manifest.json"])
    record = manifest["outputs"]["daily_logic"]
    assert record["sha256"] == hashlib.sha256(
        artifact_bytes["daily_logic.json"]
    ).hexdigest()
    assert record["bytes"] == len(artifact_bytes["daily_logic.json"])


def test_output_has_no_downstream_research_or_portfolio_fields(
    artifact_bytes: dict[str, bytes]
) -> None:
    combined = b"\n".join(artifact_bytes.values()).decode("utf-8")
    forbidden = (
        "event_id",
        "event_start",
        "event_end",
        "event_duration",
        "trigger_date",
        "execution_date",
        "forward_return",
        "outcome",
        "best_profile",
        "selected_profile",
        "target_weight",
        "position",
        "transaction_cost",
        "Sharpe",
        "Calmar",
        "maximum_drawdown",
    )
    assert not any(term in combined for term in forbidden)


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
    assert (target / "old.json").read_text(encoding="utf-8") == '{"old":true}\n'


def test_formal_input_and_output_boundaries() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden_inputs = (
        "data/strategy_style_research/prices",
        "data/research_prices",
        "reports/current",
        "reports/strategy_research",
        "current_taa",
        "shadow-portfolio",
        "execution-backtest",
    )
    assert not any(term in source for term in forbidden_inputs)
    output_dir = ROOT / MODULE.OUTPUT_DIR
    if output_dir.exists():
        assert {path.name for path in output_dir.iterdir() if path.is_file()} == {
            "manifest.json",
            "daily_logic.json",
        }

