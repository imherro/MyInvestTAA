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
SCRIPT = ROOT / "scripts/build_strategy_style_logic_events.py"
SPEC = importlib.util.spec_from_file_location("strategy_style_logic_events", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _dates() -> list[str]:
    return [f"D{index:04d}" for index in range(MODULE.DATE_COUNT - 1)] + [
        MODULE.AS_OF
    ]


def _stream(
    transitions: dict[int, tuple[str, str, str]], style: str = "growth"
) -> dict[str, Any]:
    before = ["INACTIVE"] * MODULE.DATE_COUNT
    results = ["NO_CHANGE"] * MODULE.DATE_COUNT
    after = ["INACTIVE"] * MODULE.DATE_COUNT
    current = "INACTIVE"
    for index in range(MODULE.DATE_COUNT):
        if index in transitions:
            expected_before, result, state_after = transitions[index]
            assert current == expected_before
        else:
            result = "HOLD_CANDIDATE" if current == "ACTIVE" else "NO_CHANGE"
            state_after = current
        before[index] = current
        results[index] = result
        after[index] = state_after
        current = state_after
    return {
        "style_unit": style,
        "member_asset_ids": MODULE.STYLE_MEMBERS[style],
        "state_before": before,
        "daily_result": results,
        "state_after": after,
    }


def _copy_inputs(target: Path) -> None:
    for relative in (
        MODULE.DAILY_LOGIC_MANIFEST,
        MODULE.DAILY_LOGIC,
        MODULE.COMMON_PANEL,
        MODULE.EVENT_CONTRACT,
        MODULE.STATE_MACHINE_CONTRACT,
    ):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)


@pytest.fixture(scope="session")
def artifact_bytes() -> dict[str, bytes]:
    return MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF)


@pytest.fixture(scope="session")
def decoded(artifact_bytes: dict[str, bytes]) -> dict[str, Any]:
    return {name: json.loads(content) for name, content in artifact_bytes.items()}


def test_formal_source_chain_and_wrong_as_of() -> None:
    validated = MODULE.load_and_validate_inputs(ROOT, MODULE.AS_OF)
    assert len(validated["dates"]) == 3284
    assert validated["dates"][0] == "2013-01-04"
    assert validated["dates"][-1] == MODULE.AS_OF
    with pytest.raises(MODULE.StrategyStyleLogicEventError, match="--as-of"):
        MODULE.load_and_validate_inputs(ROOT, "2026-07-14")


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        (MODULE.DAILY_LOGIC_MANIFEST, "manifest formal hash"),
        (MODULE.DAILY_LOGIC, "daily logic hash"),
        (MODULE.COMMON_PANEL, "common panel hash"),
        (MODULE.EVENT_CONTRACT, "formal hash|input"),
        (MODULE.STATE_MACHINE_CONTRACT, "contract hash"),
    ],
)
def test_tampered_source_fails(
    tmp_path: Path, relative: Path, message: str
) -> None:
    _copy_inputs(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b" \n")
    with pytest.raises(MODULE.StrategyStyleLogicEventError, match=message):
        MODULE.load_and_validate_inputs(tmp_path, MODULE.AS_OF)


def test_builder_is_offline_and_ignores_credentials(
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
        "events.json",
    }
    source = SCRIPT.read_text(encoding="utf-8")
    assert "TUSHARE_TOKEN" not in source
    assert 'root / ".env"' not in source


def test_single_closed_event_includes_endpoints_and_counts_blocked_hold() -> None:
    stream = _stream(
        {
            2: ("INACTIVE", "ENTRY_CANDIDATE", "ACTIVE"),
            4: ("ACTIVE", "BLOCKED", "ACTIVE"),
            6: ("ACTIVE", "EXIT_CANDIDATE", "INACTIVE"),
        }
    )
    events = MODULE.build_stream_events(
        "PROFILE_A", "growth", stream, _dates()
    )
    assert len(events) == 1
    event = events[0]
    assert event["event_id"] == "PROFILE_A__growth__0001"
    assert event["event_status"] == "CLOSED"
    assert event["event_start_index"] == 2
    assert event["event_end_index"] == 6
    assert event["last_observation_index"] == 6
    assert event["last_observation_date"] == event["event_end_observation_date"]
    assert event["observation_session_count"] == 5
    assert event["blocked_session_count"] == 1
    assert event["hold_session_count"] == 2
    assert event["source_exit_result"] == "EXIT_CANDIDATE"


def test_single_open_event_uses_sample_end_last_observation() -> None:
    stream = _stream(
        {3283: ("INACTIVE", "ENTRY_CANDIDATE", "ACTIVE")}
    )
    event = MODULE.build_stream_events(
        "PROFILE_C", "growth", stream, _dates()
    )[0]
    assert event["event_status"] == "OPEN"
    assert event["event_end_index"] is None
    assert event["event_end_observation_date"] is None
    assert event["last_observation_index"] == 3283
    assert event["last_observation_date"] == MODULE.AS_OF
    assert event["observation_session_count"] == 1
    assert event["source_exit_result"] is None


def test_blocked_and_hold_do_not_split_or_create_events() -> None:
    stream = _stream(
        {
            1: ("INACTIVE", "BLOCKED", "INACTIVE"),
            2: ("INACTIVE", "ENTRY_CANDIDATE", "ACTIVE"),
            3: ("ACTIVE", "BLOCKED", "ACTIVE"),
            5: ("ACTIVE", "EXIT_CANDIDATE", "INACTIVE"),
        }
    )
    events = MODULE.build_stream_events(
        "PROFILE_A", "growth", stream, _dates()
    )
    assert len(events) == 1
    assert events[0]["event_start_index"] == 2
    assert events[0]["blocked_session_count"] == 1
    assert events[0]["hold_session_count"] == 1


def test_first_exit_closes_and_reentry_creates_new_unmerged_event() -> None:
    stream = _stream(
        {
            0: ("INACTIVE", "ENTRY_CANDIDATE", "ACTIVE"),
            2: ("ACTIVE", "EXIT_CANDIDATE", "INACTIVE"),
            3: ("INACTIVE", "ENTRY_CANDIDATE", "ACTIVE"),
            4: ("ACTIVE", "EXIT_CANDIDATE", "INACTIVE"),
        }
    )
    events = MODULE.build_stream_events(
        "PROFILE_A", "growth", stream, _dates()
    )
    assert [(row["sequence_number"], row["event_start_index"], row["event_end_index"]) for row in events] == [
        (1, 0, 2),
        (2, 3, 4),
    ]
    assert events[0]["event_id"] == "PROFILE_A__growth__0001"
    assert events[1]["event_id"] == "PROFILE_A__growth__0002"


def test_exit_without_entry_and_entry_while_open_fail() -> None:
    exit_without_entry = {
        "state_before": ["ACTIVE"],
        "daily_result": ["EXIT_CANDIDATE"],
        "state_after": ["INACTIVE"],
    }
    with pytest.raises(MODULE.StrategyStyleLogicEventError, match="without open"):
        MODULE.build_stream_events(
            "PROFILE_A", "growth", exit_without_entry, ["D0"]
        )
    entry_while_open = {
        "state_before": ["INACTIVE", "INACTIVE"],
        "daily_result": ["ENTRY_CANDIDATE", "ENTRY_CANDIDATE"],
        "state_after": ["ACTIVE", "ACTIVE"],
    }
    with pytest.raises(MODULE.StrategyStyleLogicEventError, match="while event"):
        MODULE.build_stream_events(
            "PROFILE_A", "growth", entry_while_open, ["D0", "D1"]
        )


def test_formal_event_top_level_counts_and_fixed_axes(
    decoded: dict[str, Any]
) -> None:
    events = decoded["events.json"]
    assert events["dataset_id"] == "STRATEGY_STYLE_LOGIC_EVENTS_V1"
    assert events["date_count"] == 3284
    assert events["date_axis"] == "common_panel.dates"
    assert events["profile_order"] == list(MODULE.PROFILE_ORDER)
    assert events["style_order"] == list(MODULE.STYLE_ORDER)
    assert events["event_status_values"] == ["CLOSED", "OPEN"]
    assert events["event_stream_count"] == 12
    assert events["event_count"] == len(events["events"])
    assert events["closed_event_count"] + events["open_event_count"] == events[
        "event_count"
    ]


def test_formal_events_have_exact_fields_dates_and_last_observation(
    decoded: dict[str, Any]
) -> None:
    events = decoded["events.json"]["events"]
    dates = json.loads((ROOT / MODULE.COMMON_PANEL).read_text(encoding="utf-8"))[
        "dates"
    ]
    assert all(set(event) == MODULE.EVENT_FIELDS for event in events)
    for event in events:
        assert event["event_start_observation_date"] == dates[
            event["event_start_index"]
        ]
        assert event["last_observation_date"] == dates[
            event["last_observation_index"]
        ]
        if event["event_status"] == "CLOSED":
            assert event["last_observation_index"] == event["event_end_index"]
            assert event["last_observation_date"] == event[
                "event_end_observation_date"
            ]
        else:
            assert event["event_end_index"] is None
            assert event["event_end_observation_date"] is None
            assert event["last_observation_index"] == 3283
            assert event["last_observation_date"] == MODULE.AS_OF


def test_formal_entry_exit_correspondence_counts_and_no_overlap(
    decoded: dict[str, Any]
) -> None:
    events = decoded["events.json"]["events"]
    logic = json.loads((ROOT / MODULE.DAILY_LOGIC).read_text(encoding="utf-8"))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault((event["profile_id"], event["style_unit"]), []).append(
            event
        )
    for profile in logic["profiles"]:
        for style in profile["style_logic"]:
            stream = grouped.get((profile["profile_id"], style["style_unit"]), [])
            results = style["daily_result"]
            assert len(stream) == results.count("ENTRY_CANDIDATE")
            assert sum(event["event_status"] == "CLOSED" for event in stream) == results.count(
                "EXIT_CANDIDATE"
            )
            assert [event["sequence_number"] for event in stream] == list(
                range(1, len(stream) + 1)
            )
            assert all(
                stream[index - 1]["last_observation_index"]
                < stream[index]["event_start_index"]
                for index in range(1, len(stream))
            )
            assert sum(event["event_status"] == "OPEN" for event in stream) <= 1
            if stream and stream[-1]["event_status"] == "OPEN":
                assert all(event["event_status"] == "CLOSED" for event in stream[:-1])


def test_formal_blocked_hold_counts_ids_and_global_order(
    decoded: dict[str, Any]
) -> None:
    events = decoded["events.json"]["events"]
    logic = json.loads((ROOT / MODULE.DAILY_LOGIC).read_text(encoding="utf-8"))
    logic_map = {
        (profile["profile_id"], style["style_unit"]): style["daily_result"]
        for profile in logic["profiles"]
        for style in profile["style_logic"]
    }
    ids = []
    sort_keys = []
    for event in events:
        ids.append(event["event_id"])
        sort_keys.append(
            (
                MODULE.PROFILE_ORDER.index(event["profile_id"]),
                MODULE.STYLE_ORDER.index(event["style_unit"]),
                event["sequence_number"],
            )
        )
        expected_id = f"{event['profile_id']}__{event['style_unit']}__{event['sequence_number']:04d}"
        assert event["event_id"] == expected_id
        results = logic_map[(event["profile_id"], event["style_unit"])]
        interval = results[
            event["event_start_index"] : event["last_observation_index"] + 1
        ]
        assert event["blocked_session_count"] == interval.count("BLOCKED")
        assert event["hold_session_count"] == interval.count("HOLD_CANDIDATE")
    assert len(ids) == len(set(ids))
    assert sort_keys == sorted(sort_keys)


def test_same_day_different_styles_and_dividend_are_independent(
    decoded: dict[str, Any]
) -> None:
    events = decoded["events.json"]["events"]
    starts: dict[tuple[str, int], set[str]] = {}
    for event in events:
        starts.setdefault(
            (event["profile_id"], event["event_start_index"]), set()
        ).add(event["style_unit"])
    assert any(len(styles) > 1 for styles in starts.values())
    assert all(event["member_asset_ids"] == MODULE.STYLE_MEMBERS[event["style_unit"]] for event in events)
    assert all(event["style_unit"] != "H00015.CSI" for event in events)


def test_deterministic_bytes_and_manifest_output_hash(
    artifact_bytes: dict[str, bytes]
) -> None:
    assert MODULE.build_artifact_bytes(ROOT, MODULE.AS_OF) == artifact_bytes
    manifest = json.loads(artifact_bytes["manifest.json"])
    record = manifest["outputs"]["events"]
    assert record["sha256"] == hashlib.sha256(
        artifact_bytes["events.json"]
    ).hexdigest()
    assert record["bytes"] == len(artifact_bytes["events.json"])


def test_no_forbidden_results_prices_selection_or_portfolio_fields(
    artifact_bytes: dict[str, bytes]
) -> None:
    events_text = artifact_bytes["events.json"].decode("utf-8")
    forbidden = (
        "trigger_price",
        "entry_price",
        "exit_price",
        "execution_date",
        "trade_date",
        "position",
        "weight",
        "allocation",
        "capital",
        "transaction_cost",
        "forward_return",
        "event_return",
        "annualized_return",
        "excess_return",
        "maximum_drawdown",
        "outcome",
        "best_profile",
        "selected_profile",
        "profile_rank",
        "style_rank",
    )
    assert not any(term in events_text for term in forbidden)


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


def test_formal_input_and_output_boundaries() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden_inputs = (
        "category_states.json",
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
            "events.json",
        }

