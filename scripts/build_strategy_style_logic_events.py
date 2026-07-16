"""Build deterministic event facts from the frozen daily logic artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-07-15"
DAILY_LOGIC_DIR = Path("data/strategy_style_daily_logic_v1")
DAILY_LOGIC_MANIFEST = DAILY_LOGIC_DIR / "manifest.json"
DAILY_LOGIC = DAILY_LOGIC_DIR / "daily_logic.json"
COMMON_PANEL = Path("data/strategy_style_category_calculations_v1/common_panel.json")
EVENT_CONTRACT = Path(
    "docs/STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1.md"
)
STATE_MACHINE_CONTRACT = Path(
    "docs/STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md"
)
OUTPUT_DIR = Path("data/strategy_style_logic_events_v1")
PROFILE_ORDER = ("PROFILE_A", "PROFILE_B", "PROFILE_C")
STYLE_ORDER = ("growth", "value", "dividend", "cash_flow")
STYLE_MEMBERS = {
    "growth": ["CN2296.CNI"],
    "value": ["CN2371.CNI"],
    "dividend": ["H00015.CSI", "H00922.CSI"],
    "cash_flow": ["480092.CNI"],
}
LOGICAL_STATES = {"INACTIVE", "ACTIVE"}
DAILY_RESULTS = {
    "BLOCKED",
    "NO_CHANGE",
    "ENTRY_CANDIDATE",
    "HOLD_CANDIDATE",
    "EXIT_CANDIDATE",
}
ALLOWED_TRANSITIONS = {
    ("INACTIVE", "BLOCKED", "INACTIVE"),
    ("INACTIVE", "NO_CHANGE", "INACTIVE"),
    ("INACTIVE", "ENTRY_CANDIDATE", "ACTIVE"),
    ("ACTIVE", "BLOCKED", "ACTIVE"),
    ("ACTIVE", "HOLD_CANDIDATE", "ACTIVE"),
    ("ACTIVE", "EXIT_CANDIDATE", "INACTIVE"),
}
EVENT_FIELDS = {
    "event_id",
    "profile_id",
    "style_unit",
    "member_asset_ids",
    "sequence_number",
    "event_status",
    "event_start_index",
    "event_start_observation_date",
    "event_end_index",
    "event_end_observation_date",
    "last_observation_index",
    "last_observation_date",
    "observation_session_count",
    "blocked_session_count",
    "hold_session_count",
    "source_entry_result",
    "source_exit_result",
}
DATE_COUNT = 3284
EXPECTED_DAILY_MANIFEST_SHA = (
    "8d5f4c9106fb23169169acc8f4dbad5187f72bca95c4e1865a2b4c755e5cbc25"
)
EXPECTED_DAILY_MANIFEST_BYTES = 1584
EXPECTED_EVENT_CONTRACT_SHA = (
    "fe3e91bd50291c88be5f1c30536ca88c9c64787a90766c03768669ebfbfbc17a"
)
EXPECTED_EVENT_CONTRACT_BYTES = 9738


class StrategyStyleLogicEventError(RuntimeError):
    """Raised when formal inputs or event facts violate the frozen contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StrategyStyleLogicEventError(message)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _read_bytes(root: Path, relative: Path) -> bytes:
    try:
        return (root / relative).read_bytes()
    except OSError as exc:
        raise StrategyStyleLogicEventError(
            f"cannot read formal input: {relative}"
        ) from exc


def _read_json(root: Path, relative: Path) -> tuple[dict[str, Any], bytes]:
    content = _read_bytes(root, relative)
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StrategyStyleLogicEventError(f"invalid JSON input: {relative}") from exc
    _require(isinstance(value, dict), f"formal input must be an object: {relative}")
    return value, content


def _source_record(relative: Path, content: bytes) -> dict[str, Any]:
    return {
        "path": relative.as_posix(),
        "sha256": sha256_bytes(content),
        "bytes": len(content),
    }


def load_and_validate_inputs(root: Path, as_of: str) -> dict[str, Any]:
    """Load only daily logic, its date axis, and the two frozen contracts."""
    _require(as_of == AS_OF, f"--as-of must be {AS_OF}")
    manifest, manifest_bytes = _read_json(root, DAILY_LOGIC_MANIFEST)
    logic, logic_bytes = _read_json(root, DAILY_LOGIC)
    panel, panel_bytes = _read_json(root, COMMON_PANEL)
    event_contract_bytes = _read_bytes(root, EVENT_CONTRACT)
    state_contract_bytes = _read_bytes(root, STATE_MACHINE_CONTRACT)

    _require(
        sha256_bytes(manifest_bytes) == EXPECTED_DAILY_MANIFEST_SHA,
        "daily logic manifest formal hash mismatch",
    )
    _require(
        len(manifest_bytes) == EXPECTED_DAILY_MANIFEST_BYTES,
        "daily logic manifest formal byte count mismatch",
    )
    _require(
        sha256_bytes(event_contract_bytes) == EXPECTED_EVENT_CONTRACT_SHA,
        "event contract formal hash mismatch",
    )
    _require(
        len(event_contract_bytes) == EXPECTED_EVENT_CONTRACT_BYTES,
        "event contract formal byte count mismatch",
    )
    _require(
        manifest.get("artifact_set_id")
        == "STRATEGY_STYLE_DAILY_LOGIC_ARTIFACT_V1",
        "daily logic artifact set mismatch",
    )
    _require(manifest.get("source_as_of_date") == as_of, "daily logic as-of mismatch")
    expected_statuses = {
        "common_panel_status": "BUILT",
        "category_calculation_status": "IMPLEMENTED",
        "parameter_selection_status": "NOT_RUN",
        "entry_exit_state_machine_status": "IMPLEMENTED",
        "event_status": "NOT_BUILT",
        "walk_forward_status": "NOT_RUN",
        "allocation_status": "NOT_DEFINED",
        "backtest_status": "NOT_RUN",
        "integration_status": "DO_NOT_INTEGRATE",
    }
    for key, expected in expected_statuses.items():
        _require(
            manifest.get("statuses", {}).get(key) == expected,
            f"daily logic status mismatch: {key}",
        )
    expected_invariants = {
        "date_count": DATE_COUNT,
        "profile_count": 3,
        "style_count": 4,
        "event_free": True,
        "offline_only": True,
        "no_forward_information": True,
    }
    for key, expected in expected_invariants.items():
        _require(
            manifest.get("invariants", {}).get(key) == expected,
            f"daily logic invariant mismatch: {key}",
        )

    logic_record = manifest.get("outputs", {}).get("daily_logic", {})
    _require(logic_record.get("path") == DAILY_LOGIC.as_posix(), "daily logic path mismatch")
    _require(logic_record.get("sha256") == sha256_bytes(logic_bytes), "daily logic hash mismatch")
    _require(logic_record.get("bytes") == len(logic_bytes), "daily logic byte count mismatch")
    panel_record = manifest.get("source_files", {}).get("common_panel", {})
    _require(panel_record.get("path") == COMMON_PANEL.as_posix(), "common panel path mismatch")
    _require(panel_record.get("sha256") == sha256_bytes(panel_bytes), "common panel hash mismatch")
    _require(panel_record.get("bytes") == len(panel_bytes), "common panel byte count mismatch")

    state_contract_record = manifest.get("source_contracts", {}).get(
        "STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1", {}
    )
    _require(
        state_contract_record.get("path") == STATE_MACHINE_CONTRACT.as_posix(),
        "state-machine contract path mismatch",
    )
    _require(
        state_contract_record.get("sha256") == sha256_bytes(state_contract_bytes),
        "state-machine contract hash mismatch",
    )
    _require(
        state_contract_record.get("bytes") == len(state_contract_bytes),
        "state-machine contract byte count mismatch",
    )
    _require(
        logic.get("source_state_machine_contract_sha256")
        == state_contract_record.get("sha256"),
        "daily logic state-machine contract hash mismatch",
    )
    _require(logic.get("source_common_panel_path") == COMMON_PANEL.as_posix(), "daily logic panel path mismatch")
    _require(logic.get("source_common_panel_sha256") == sha256_bytes(panel_bytes), "daily logic panel hash mismatch")

    dates = panel.get("dates")
    _require(isinstance(dates, list) and len(dates) == DATE_COUNT, "common date count mismatch")
    _require(dates[0] == "2013-01-04" and dates[-1] == as_of, "common date bounds mismatch")
    _require(dates == sorted(set(dates)), "common dates must be sorted and unique")
    _require(all(date <= as_of for date in dates), "common panel contains future date")

    _require(logic.get("dataset_id") == "STRATEGY_STYLE_DAILY_LOGIC_V1", "daily logic dataset id mismatch")
    _require(logic.get("source_as_of_date") == as_of, "daily logic source as-of mismatch")
    _require(logic.get("date_count") == DATE_COUNT, "daily logic date count mismatch")
    _require(logic.get("date_axis") == "common_panel.dates", "daily logic date axis mismatch")
    _require(logic.get("profile_order") == list(PROFILE_ORDER), "daily logic profile order mismatch")
    _require(logic.get("style_order") == list(STYLE_ORDER), "daily logic style order mismatch")
    _require(set(logic.get("logical_state_values", [])) == LOGICAL_STATES, "logical state enum mismatch")
    _require(set(logic.get("daily_result_values", [])) == DAILY_RESULTS, "daily result enum mismatch")
    profiles = logic.get("profiles")
    _require(isinstance(profiles, list), "daily logic profiles must be an array")
    _require([row.get("profile_id") for row in profiles] == list(PROFILE_ORDER), "daily logic profiles mismatch")
    for profile in profiles:
        styles = profile.get("style_logic")
        _require(isinstance(styles, list), "style logic must be an array")
        _require([row.get("style_unit") for row in styles] == list(STYLE_ORDER), "style logic order mismatch")
        concurrent = profile.get("concurrent_entry_candidate_set")
        _require(isinstance(concurrent, list) and len(concurrent) == DATE_COUNT, "concurrent set length mismatch")
        for style, expected_style in zip(styles, STYLE_ORDER, strict=True):
            _require(style.get("member_asset_ids") == STYLE_MEMBERS[expected_style], f"member map mismatch: {expected_style}")
            before = style.get("state_before")
            results = style.get("daily_result")
            after = style.get("state_after")
            _require(all(isinstance(values, list) and len(values) == DATE_COUNT for values in (before, results, after)), f"daily array length mismatch: {expected_style}")
            _require(before[0] == "INACTIVE", f"initial state mismatch: {expected_style}")
            _require(set(before) <= LOGICAL_STATES and set(after) <= LOGICAL_STATES, f"logical state value mismatch: {expected_style}")
            _require(set(results) <= DAILY_RESULTS, f"daily result value mismatch: {expected_style}")
            _require(all(row in ALLOWED_TRANSITIONS for row in zip(before, results, after, strict=True)), f"invalid transition: {expected_style}")
            _require(all(before[index] == after[index - 1] for index in range(1, DATE_COUNT)), f"state recurrence mismatch: {expected_style}")
        for index, candidates in enumerate(concurrent):
            expected = [style["style_unit"] for style in styles if style["daily_result"][index] == "ENTRY_CANDIDATE"]
            _require(candidates == expected, "concurrent entry set mismatch")

    return {
        "manifest": manifest,
        "logic": logic,
        "dates": dates,
        "source_files": {
            "daily_logic_manifest": _source_record(DAILY_LOGIC_MANIFEST, manifest_bytes),
            "daily_logic": _source_record(DAILY_LOGIC, logic_bytes),
            "common_panel": _source_record(COMMON_PANEL, panel_bytes),
        },
        "source_contracts": {
            "STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1": _source_record(EVENT_CONTRACT, event_contract_bytes),
            "STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1": _source_record(STATE_MACHINE_CONTRACT, state_contract_bytes),
        },
    }


def _new_event(
    profile_id: str,
    style: str,
    sequence_number: int,
    start_index: int,
    dates: list[str],
) -> dict[str, Any]:
    return {
        "event_id": f"{profile_id}__{style}__{sequence_number:04d}",
        "profile_id": profile_id,
        "style_unit": style,
        "member_asset_ids": STYLE_MEMBERS[style],
        "sequence_number": sequence_number,
        "event_status": None,
        "event_start_index": start_index,
        "event_start_observation_date": dates[start_index],
        "event_end_index": None,
        "event_end_observation_date": None,
        "last_observation_index": None,
        "last_observation_date": None,
        "observation_session_count": None,
        "blocked_session_count": 0,
        "hold_session_count": 0,
        "source_entry_result": "ENTRY_CANDIDATE",
        "source_exit_result": None,
    }


def build_stream_events(
    profile_id: str,
    style: str,
    style_logic: dict[str, Any],
    dates: list[str],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    sequence_number = 0
    before = style_logic["state_before"]
    results = style_logic["daily_result"]
    after = style_logic["state_after"]
    for index, (state_before, result, state_after) in enumerate(
        zip(before, results, after, strict=True)
    ):
        if result == "ENTRY_CANDIDATE":
            _require(
                (state_before, state_after) == ("INACTIVE", "ACTIVE"),
                "ENTRY transition mismatch",
            )
            _require(current is None, "ENTRY encountered while event is open")
            sequence_number += 1
            current = _new_event(
                profile_id, style, sequence_number, index, dates
            )
        elif result == "EXIT_CANDIDATE":
            _require(
                (state_before, state_after) == ("ACTIVE", "INACTIVE"),
                "EXIT transition mismatch",
            )
            _require(current is not None, "EXIT encountered without open event")
            current["event_status"] = "CLOSED"
            current["event_end_index"] = index
            current["event_end_observation_date"] = dates[index]
            current["last_observation_index"] = index
            current["last_observation_date"] = dates[index]
            current["observation_session_count"] = (
                index - current["event_start_index"] + 1
            )
            current["source_exit_result"] = "EXIT_CANDIDATE"
            _require(
                current["observation_session_count"] >= 2,
                "CLOSED event must span at least two observations",
            )
            events.append(current)
            current = None
        elif current is not None and result == "BLOCKED":
            current["blocked_session_count"] += 1
        elif current is not None and result == "HOLD_CANDIDATE":
            current["hold_session_count"] += 1
    if current is not None:
        current["event_status"] = "OPEN"
        current["last_observation_index"] = DATE_COUNT - 1
        current["last_observation_date"] = dates[-1]
        current["observation_session_count"] = (
            DATE_COUNT - current["event_start_index"]
        )
        events.append(current)
    return events


def build_events(validated: dict[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for profile in validated["logic"]["profiles"]:
        for style, style_logic in zip(
            STYLE_ORDER, profile["style_logic"], strict=True
        ):
            events.extend(
                build_stream_events(
                    profile["profile_id"],
                    style,
                    style_logic,
                    validated["dates"],
                )
            )
    closed_count = sum(event["event_status"] == "CLOSED" for event in events)
    open_count = sum(event["event_status"] == "OPEN" for event in events)
    source_files = validated["source_files"]
    source_contracts = validated["source_contracts"]
    return {
        "schema_version": "1.0",
        "dataset_id": "STRATEGY_STYLE_LOGIC_EVENTS_V1",
        "source_as_of_date": AS_OF,
        "source_daily_logic_manifest_path": DAILY_LOGIC_MANIFEST.as_posix(),
        "source_daily_logic_manifest_sha256": source_files[
            "daily_logic_manifest"
        ]["sha256"],
        "source_daily_logic_path": DAILY_LOGIC.as_posix(),
        "source_daily_logic_sha256": source_files["daily_logic"]["sha256"],
        "source_common_panel_path": COMMON_PANEL.as_posix(),
        "source_common_panel_sha256": source_files["common_panel"]["sha256"],
        "source_event_contract_sha256": source_contracts[
            "STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1"
        ]["sha256"],
        "date_count": DATE_COUNT,
        "date_axis": "common_panel.dates",
        "profile_order": list(PROFILE_ORDER),
        "style_order": list(STYLE_ORDER),
        "event_status_values": ["CLOSED", "OPEN"],
        "event_stream_count": len(PROFILE_ORDER) * len(STYLE_ORDER),
        "event_count": len(events),
        "closed_event_count": closed_count,
        "open_event_count": open_count,
        "events": events,
    }


def validate_events_dataset(
    dataset: dict[str, Any], validated: dict[str, Any]
) -> None:
    events = dataset["events"]
    _require(dataset["event_count"] == len(events), "event count mismatch")
    _require(dataset["closed_event_count"] == sum(row["event_status"] == "CLOSED" for row in events), "closed event count mismatch")
    _require(dataset["open_event_count"] == sum(row["event_status"] == "OPEN" for row in events), "open event count mismatch")
    _require(dataset["event_stream_count"] == 12, "event stream count mismatch")
    _require(all(set(event) == EVENT_FIELDS for event in events), "event field inventory mismatch")
    _require(len({event["event_id"] for event in events}) == len(events), "event ids are not unique")
    dates = validated["dates"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in events:
        _require(event["event_status"] in {"CLOSED", "OPEN"}, "invalid event status")
        _require(event["member_asset_ids"] == STYLE_MEMBERS[event["style_unit"]], "event member map mismatch")
        _require(event["event_start_observation_date"] == dates[event["event_start_index"]], "event start date mismatch")
        _require(event["last_observation_date"] == dates[event["last_observation_index"]], "last observation date mismatch")
        _require(event["last_observation_index"] >= event["event_start_index"], "last observation precedes event start")
        expected_id = f"{event['profile_id']}__{event['style_unit']}__{event['sequence_number']:04d}"
        _require(event["event_id"] == expected_id, "event id mismatch")
        if event["event_status"] == "CLOSED":
            _require(event["event_end_index"] is not None, "CLOSED event end missing")
            _require(event["event_end_observation_date"] == dates[event["event_end_index"]], "CLOSED event end date mismatch")
            _require(event["last_observation_index"] == event["event_end_index"], "CLOSED last observation mismatch")
            _require(event["last_observation_date"] == event["event_end_observation_date"], "CLOSED last date mismatch")
            _require(event["source_exit_result"] == "EXIT_CANDIDATE", "CLOSED exit source mismatch")
        else:
            _require(event["event_end_index"] is None and event["event_end_observation_date"] is None, "OPEN event end must be null")
            _require(event["last_observation_index"] == DATE_COUNT - 1, "OPEN last index mismatch")
            _require(event["last_observation_date"] == AS_OF, "OPEN last date mismatch")
            _require(event["source_exit_result"] is None, "OPEN exit source must be null")
        _require(event["observation_session_count"] == event["last_observation_index"] - event["event_start_index"] + 1, "observation count mismatch")
        grouped.setdefault((event["profile_id"], event["style_unit"]), []).append(event)

    logic_profiles = {
        profile["profile_id"]: profile for profile in validated["logic"]["profiles"]
    }
    expected_global_order: list[str] = []
    for profile_id in PROFILE_ORDER:
        profile = logic_profiles[profile_id]
        for style, style_logic in zip(STYLE_ORDER, profile["style_logic"], strict=True):
            stream = grouped.get((profile_id, style), [])
            _require([row["sequence_number"] for row in stream] == list(range(1, len(stream) + 1)), "event sequence is not continuous")
            _require(all(stream[index - 1]["last_observation_index"] < stream[index]["event_start_index"] for index in range(1, len(stream))), "events overlap")
            _require(sum(row["event_status"] == "OPEN" for row in stream) <= 1, "multiple OPEN events in stream")
            if any(row["event_status"] == "OPEN" for row in stream):
                _require(stream[-1]["event_status"] == "OPEN", "OPEN event is not last in stream")
            expected_global_order.extend(row["event_id"] for row in stream)
            results = style_logic["daily_result"]
            _require(len(stream) == results.count("ENTRY_CANDIDATE"), "ENTRY-to-event correspondence mismatch")
            _require(sum(row["event_status"] == "CLOSED" for row in stream) == results.count("EXIT_CANDIDATE"), "EXIT-to-event correspondence mismatch")
            for event in stream:
                start = event["event_start_index"]
                end = event["last_observation_index"]
                _require(results[start] == "ENTRY_CANDIDATE", "event does not start at ENTRY")
                if event["event_status"] == "CLOSED":
                    _require(results[event["event_end_index"]] == "EXIT_CANDIDATE", "event does not end at EXIT")
                    _require("EXIT_CANDIDATE" not in results[start + 1 : event["event_end_index"]], "event skipped earlier EXIT")
                _require(event["blocked_session_count"] == results[start : end + 1].count("BLOCKED"), "blocked count mismatch")
                _require(event["hold_session_count"] == results[start : end + 1].count("HOLD_CANDIDATE"), "hold count mismatch")
    _require([event["event_id"] for event in events] == expected_global_order, "global event order mismatch")


def build_artifact_bytes(root: Path, as_of: str) -> dict[str, bytes]:
    validated = load_and_validate_inputs(root, as_of)
    events = build_events(validated)
    validate_events_dataset(events, validated)
    events_content = json_bytes(events)
    manifest = {
        "schema_version": "1.0",
        "artifact_set_id": "STRATEGY_STYLE_LOGIC_EVENTS_ARTIFACT_V1",
        "source_as_of_date": as_of,
        "source_files": validated["source_files"],
        "source_contracts": validated["source_contracts"],
        "outputs": {
            "events": {
                "path": f"{OUTPUT_DIR.as_posix()}/events.json",
                "sha256": sha256_bytes(events_content),
                "bytes": len(events_content),
            }
        },
        "invariants": {
            "date_count": DATE_COUNT,
            "profile_count": 3,
            "style_count": 4,
            "event_stream_count": 12,
            "event_count": events["event_count"],
            "closed_event_count": events["closed_event_count"],
            "open_event_count": events["open_event_count"],
            "offline_only": True,
            "no_forward_information": True,
            "event_facts_only": True,
        },
        "statuses": {
            "daily_logic_state_machine_status": "IMPLEMENTED",
            "event_construction_implementation_status": "IMPLEMENTED",
            "event_dataset_status": "BUILT",
            "forward_outcome_status": "NOT_COMPUTED",
            "walk_forward_status": "NOT_RUN",
            "parameter_profile_selection_status": "NOT_RUN",
            "allocation_status": "NOT_DEFINED",
            "backtest_status": "NOT_RUN",
            "integration_status": "DO_NOT_INTEGRATE",
        },
    }
    artifacts = {
        "manifest.json": json_bytes(manifest),
        "events.json": events_content,
    }
    validate_artifact_bytes(artifacts)
    return artifacts


def validate_artifact_bytes(artifacts: dict[str, bytes]) -> None:
    _require(set(artifacts) == {"manifest.json", "events.json"}, "artifact inventory mismatch")
    manifest = json.loads(artifacts["manifest.json"])
    events = json.loads(artifacts["events.json"])
    output = manifest["outputs"]["events"]
    _require(output["sha256"] == sha256_bytes(artifacts["events.json"]), "manifest output hash mismatch")
    _require(output["bytes"] == len(artifacts["events.json"]), "manifest output byte count mismatch")
    for key in ("event_count", "closed_event_count", "open_event_count"):
        _require(manifest["invariants"][key] == events[key], f"manifest invariant mismatch: {key}")
    forbidden = (
        "trigger_price", "entry_price", "exit_price", "execution_date",
        "trade_date", "position", "weight", "capital", "transaction_cost",
        "forward_return", "event_return", "annualized_return", "excess_return",
        "maximum_drawdown", "Sharpe", "Calmar", "outcome", "success",
        "failure", "best_profile", "selected_profile", "profile_rank",
        "style_rank",
    )
    events_text = artifacts["events.json"].decode("utf-8")
    _require(not any(term in events_text for term in forbidden), "events contain forbidden result field")


def publish_artifacts(root: Path, artifacts: dict[str, bytes]) -> None:
    target = root / OUTPUT_DIR
    target.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".strategy-style-events-", dir=target.parent))
    staged = staging_root / "complete"
    backup = staging_root / "previous"
    try:
        staged.mkdir()
        for name, content in artifacts.items():
            (staged / name).write_bytes(content)
        staged_artifacts = {path.name: path.read_bytes() for path in staged.iterdir() if path.is_file()}
        validate_artifact_bytes(staged_artifacts)
        if target.exists():
            os.replace(target, backup)
        try:
            os.replace(staged, target)
        except BaseException:
            if backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


def build_strategy_style_logic_events(root: Path, as_of: str, *, publish: bool = True) -> dict[str, bytes]:
    artifacts = build_artifact_bytes(root, as_of)
    if publish:
        publish_artifacts(root, artifacts)
    return artifacts


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic strategy-style logic event facts.")
    parser.add_argument("--as-of", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        artifacts = build_strategy_style_logic_events(ROOT, args.as_of)
    except (OSError, StrategyStyleLogicEventError) as exc:
        print(f"strategy-style logic-event build failed: {exc}")
        return 1
    manifest = json.loads(artifacts["manifest.json"])
    print(f"{OUTPUT_DIR.as_posix()}: {manifest['statuses']['event_dataset_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
