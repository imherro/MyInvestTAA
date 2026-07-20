"""Build frozen strategy-style outcomes and walk-forward evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-07-15"
DATE_COUNT = 3284
EVENT_COUNT = 1122
EVENT_MANIFEST = Path("data/strategy_style_logic_events_v1/manifest.json")
EVENTS = Path("data/strategy_style_logic_events_v1/events.json")
COMMON_PANEL = Path("data/strategy_style_category_calculations_v1/common_panel.json")
OUTCOME_CONTRACT = Path(
    "docs/STRATEGY_STYLE_FORWARD_OUTCOME_WALK_FORWARD_PREREGISTRATION_V1.md"
)
EVENT_CONTRACT = Path(
    "docs/STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1.md"
)
STATE_MACHINE_CONTRACT = Path(
    "docs/STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md"
)
OUTPUT_DIR = Path("data/strategy_style_walk_forward_v1")

PROFILE_ORDER = ("PROFILE_A", "PROFILE_B", "PROFILE_C")
STYLE_ORDER = ("growth", "value", "dividend", "cash_flow")
HORIZON_ORDER = ("H20", "H60", "H120")
HORIZON_LENGTHS = {"H20": 20, "H60": 60, "H120": 120}
FORMAL_FOLD_ORDER = tuple(f"WF_{year}" for year in range(2018, 2026))
PARTITION_VALUES = (
    "DEVELOPMENT_EXCLUDED",
    "FORMAL_OOS",
    "PROSPECTIVE_NOT_SCORED",
)
AVAILABILITY_VALUES = ("AVAILABLE", "UNAVAILABLE_AS_OF", "NOT_CLOSED")
SUMMARY_STATUS_VALUES = ("AVAILABLE", "NO_ELIGIBLE_EVENTS")
PROFILE_SUPPORT_VALUES = ("WALK_FORWARD_SUPPORTED", "NOT_SUPPORTED")
MECHANISM_DECISIONS = ("REJECTED", "AMBIGUOUS", "SUPPORTED")
MINIMUM_AVAILABLE_FOLD_COUNT = 5

STYLE_MEMBERS = {
    "growth": ("CN2296.CNI",),
    "value": ("CN2371.CNI",),
    "dividend": ("H00015.CSI", "H00922.CSI"),
    "cash_flow": ("480092.CNI",),
}
MEMBER_ORDER = tuple(
    member for style in STYLE_ORDER for member in STYLE_MEMBERS[style]
)

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
OUTCOME_FIELDS = {
    "event_id",
    "profile_id",
    "style_unit",
    "event_status",
    "event_start_observation_date",
    "evaluation_start_index",
    "evaluation_start_date",
    "walk_forward_partition",
    "walk_forward_fold_id",
    "H20",
    "H60",
    "H120",
    "episode",
}
PERIOD_FIELDS = {
    "availability_status",
    "evaluation_end_index",
    "evaluation_end_date",
    "member_total_returns",
    "style_total_return",
    "peer_style_total_returns",
    "peer_benchmark_total_return",
    "peer_relative_return",
}

EXPECTED_IDENTITIES = {
    EVENT_MANIFEST: (
        "03e7e2c5b78bcb4143e11f11ed0519b4eaa6689e30f29062a78decf853d2760c",
        1886,
    ),
    EVENTS: (
        "2c1dc78144a66ffa015773742db4e4a8f5fe0d91c5140cdd952f3ecd67674b26",
        594051,
    ),
    COMMON_PANEL: (
        "f366e1d96d5804bbc512eb930e50f21fc0c652477579bc12461caf8d5f0b646c",
        1803386,
    ),
    OUTCOME_CONTRACT: (
        "9d84b4faeb3bf6f0a95a9284a151e5e2af3ebc806cc7c1c3872dee4d979bbd85",
        20603,
    ),
    EVENT_CONTRACT: (
        "fe3e91bd50291c88be5f1c30536ca88c9c64787a90766c03768669ebfbfbc17a",
        9738,
    ),
    STATE_MACHINE_CONTRACT: (
        "0ec765a0eefeedc26309d01d7d04832c88fc14ac47347d211bb5e275593c53af",
        10176,
    ),
}


class StrategyStyleWalkForwardError(RuntimeError):
    """Raised when formal inputs or outputs violate the frozen contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StrategyStyleWalkForwardError(message)


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
        raise StrategyStyleWalkForwardError(
            f"cannot read formal input: {relative}"
        ) from exc


def _read_json(root: Path, relative: Path) -> tuple[dict[str, Any], bytes]:
    content = _read_bytes(root, relative)
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StrategyStyleWalkForwardError(
            f"invalid JSON input: {relative}"
        ) from exc
    _require(isinstance(value, dict), f"formal input must be an object: {relative}")
    return value, content


def _source_record(relative: Path, content: bytes) -> dict[str, Any]:
    return {
        "path": relative.as_posix(),
        "sha256": sha256_bytes(content),
        "bytes": len(content),
    }


def _validate_identity(relative: Path, content: bytes) -> None:
    expected_hash, expected_bytes = EXPECTED_IDENTITIES[relative]
    _require(
        sha256_bytes(content) == expected_hash,
        f"formal hash mismatch: {relative}",
    )
    _require(
        len(content) == expected_bytes,
        f"formal byte count mismatch: {relative}",
    )


def _validate_event_manifest(
    manifest: dict[str, Any],
    contents: dict[Path, bytes],
) -> None:
    _require(
        manifest.get("artifact_set_id") == "STRATEGY_STYLE_LOGIC_EVENTS_ARTIFACT_V1",
        "event manifest artifact id mismatch",
    )
    _require(manifest.get("source_as_of_date") == AS_OF, "event manifest as-of mismatch")
    expected_invariants = {
        "date_count": DATE_COUNT,
        "profile_count": 3,
        "style_count": 4,
        "event_stream_count": 12,
        "event_count": EVENT_COUNT,
        "closed_event_count": 1121,
        "open_event_count": 1,
        "offline_only": True,
        "no_forward_information": True,
        "event_facts_only": True,
    }
    for key, expected in expected_invariants.items():
        _require(
            manifest.get("invariants", {}).get(key) == expected,
            f"event manifest invariant mismatch: {key}",
        )
    expected_statuses = {
        "daily_logic_state_machine_status": "IMPLEMENTED",
        "event_construction_implementation_status": "IMPLEMENTED",
        "event_dataset_status": "BUILT",
        "forward_outcome_status": "NOT_COMPUTED",
        "walk_forward_status": "NOT_RUN",
        "parameter_profile_selection_status": "NOT_RUN",
        "allocation_status": "NOT_DEFINED",
        "backtest_status": "NOT_RUN",
        "integration_status": "DO_NOT_INTEGRATE",
    }
    for key, expected in expected_statuses.items():
        _require(
            manifest.get("statuses", {}).get(key) == expected,
            f"event manifest status mismatch: {key}",
        )

    event_record = manifest.get("outputs", {}).get("events", {})
    _require(event_record.get("path") == EVENTS.as_posix(), "events path mismatch")
    _require(
        event_record.get("sha256") == sha256_bytes(contents[EVENTS]),
        "events hash mismatch",
    )
    _require(event_record.get("bytes") == len(contents[EVENTS]), "events bytes mismatch")

    panel_record = manifest.get("source_files", {}).get("common_panel", {})
    _require(panel_record.get("path") == COMMON_PANEL.as_posix(), "panel path mismatch")
    _require(
        panel_record.get("sha256") == sha256_bytes(contents[COMMON_PANEL]),
        "panel hash mismatch",
    )
    _require(panel_record.get("bytes") == len(contents[COMMON_PANEL]), "panel bytes mismatch")

    contract_records = manifest.get("source_contracts", {})
    for contract_id, path in (
        ("STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1", EVENT_CONTRACT),
        ("STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1", STATE_MACHINE_CONTRACT),
    ):
        record = contract_records.get(contract_id, {})
        _require(record.get("path") == path.as_posix(), f"contract path mismatch: {contract_id}")
        _require(
            record.get("sha256") == sha256_bytes(contents[path]),
            f"contract hash mismatch: {contract_id}",
        )
        _require(record.get("bytes") == len(contents[path]), f"contract bytes mismatch: {contract_id}")


def _validate_events_dataset(events: dict[str, Any], dates: list[str]) -> None:
    _require(events.get("dataset_id") == "STRATEGY_STYLE_LOGIC_EVENTS_V1", "event dataset id mismatch")
    _require(events.get("source_as_of_date") == AS_OF, "event dataset as-of mismatch")
    _require(events.get("date_count") == DATE_COUNT, "event date count mismatch")
    _require(events.get("date_axis") == "common_panel.dates", "event date axis mismatch")
    _require(events.get("profile_order") == list(PROFILE_ORDER), "event profile order mismatch")
    _require(events.get("style_order") == list(STYLE_ORDER), "event style order mismatch")
    _require(events.get("event_status_values") == ["CLOSED", "OPEN"], "event status values mismatch")
    _require(events.get("event_stream_count") == 12, "event stream count mismatch")
    rows = events.get("events")
    _require(isinstance(rows, list) and len(rows) == EVENT_COUNT, "event count mismatch")
    _require(events.get("event_count") == len(rows), "event top-level count mismatch")
    _require(sum(row.get("event_status") == "CLOSED" for row in rows) == 1121, "closed event count mismatch")
    _require(sum(row.get("event_status") == "OPEN" for row in rows) == 1, "open event count mismatch")
    _require(all(set(row) == EVENT_FIELDS for row in rows), "event field inventory mismatch")
    _require(len({row["event_id"] for row in rows}) == len(rows), "event ids are not unique")

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    expected_order: list[str] = []
    for row in rows:
        profile_id = row.get("profile_id")
        style = row.get("style_unit")
        _require(profile_id in PROFILE_ORDER and style in STYLE_ORDER, "event axis value mismatch")
        _require(row.get("member_asset_ids") == list(STYLE_MEMBERS[style]), "event member map mismatch")
        start = row.get("event_start_index")
        last = row.get("last_observation_index")
        _require(isinstance(start, int) and 0 <= start < DATE_COUNT, "event start index mismatch")
        _require(isinstance(last, int) and start <= last < DATE_COUNT, "event last index mismatch")
        _require(row.get("event_start_observation_date") == dates[start], "event start date mismatch")
        _require(row.get("last_observation_date") == dates[last], "event last date mismatch")
        sequence = row.get("sequence_number")
        _require(isinstance(sequence, int) and sequence >= 1, "event sequence mismatch")
        expected_id = f"{profile_id}__{style}__{sequence:04d}"
        _require(row.get("event_id") == expected_id, "event id mismatch")
        _require(
            row.get("observation_session_count") == last - start + 1,
            "event observation count mismatch",
        )
        _require(row.get("source_entry_result") == "ENTRY_CANDIDATE", "event entry source mismatch")
        if row.get("event_status") == "CLOSED":
            end = row.get("event_end_index")
            _require(isinstance(end, int) and start < end < DATE_COUNT, "CLOSED event end mismatch")
            _require(row.get("event_end_observation_date") == dates[end], "CLOSED end date mismatch")
            _require(last == end, "CLOSED last index mismatch")
            _require(row.get("source_exit_result") == "EXIT_CANDIDATE", "CLOSED exit source mismatch")
        else:
            _require(row.get("event_status") == "OPEN", "invalid event status")
            _require(row.get("event_end_index") is None, "OPEN event end must be null")
            _require(row.get("event_end_observation_date") is None, "OPEN event end date must be null")
            _require(last == DATE_COUNT - 1 and row.get("last_observation_date") == AS_OF, "OPEN last observation mismatch")
            _require(row.get("source_exit_result") is None, "OPEN exit source must be null")
        grouped.setdefault((profile_id, style), []).append(row)

    for profile_id in PROFILE_ORDER:
        for style in STYLE_ORDER:
            stream = grouped.get((profile_id, style), [])
            _require(
                [row["sequence_number"] for row in stream] == list(range(1, len(stream) + 1)),
                "event sequence is not continuous",
            )
            _require(
                all(stream[index - 1]["last_observation_index"] < stream[index]["event_start_index"] for index in range(1, len(stream))),
                "events overlap",
            )
            _require(sum(row["event_status"] == "OPEN" for row in stream) <= 1, "multiple OPEN events")
            if stream and stream[-1]["event_status"] == "OPEN":
                _require(all(row["event_status"] == "CLOSED" for row in stream[:-1]), "OPEN event is not last")
            expected_order.extend(row["event_id"] for row in stream)
    _require([row["event_id"] for row in rows] == expected_order, "event global order mismatch")


def _validate_common_panel(panel: dict[str, Any]) -> tuple[list[str], dict[str, list[float]]]:
    _require(panel.get("dataset_id") == "STRATEGY_STYLE_COMMON_PANEL_V1", "panel dataset id mismatch")
    _require(panel.get("source_as_of_date") == AS_OF, "panel as-of mismatch")
    dates = panel.get("dates")
    _require(isinstance(dates, list) and len(dates) == DATE_COUNT, "panel date count mismatch")
    _require(dates[0] == "2013-01-04" and dates[-1] == AS_OF, "panel date bounds mismatch")
    _require(dates == sorted(set(dates)), "panel dates must be sorted and unique")
    _require(panel.get("session_count") == DATE_COUNT, "panel session count mismatch")
    members = panel.get("members")
    _require(isinstance(members, list) and len(members) == len(MEMBER_ORDER), "panel member count mismatch")
    _require([row.get("asset_id") for row in members] == list(MEMBER_ORDER), "panel member order mismatch")
    close_by_member: dict[str, list[float]] = {}
    for row in members:
        asset_id = row["asset_id"]
        _require(row.get("return_basis") == "total_return", f"return basis mismatch: {asset_id}")
        close = row.get("close")
        _require(isinstance(close, list) and len(close) == DATE_COUNT, f"close length mismatch: {asset_id}")
        _require(
            all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0 for value in close),
            f"close values must be finite and positive: {asset_id}",
        )
        close_by_member[asset_id] = close
    return dates, close_by_member


def load_and_validate_inputs(root: Path, as_of: str) -> dict[str, Any]:
    """Read and validate only the frozen event, close, and contract inputs."""
    _require(as_of == AS_OF, f"--as-of must be {AS_OF}")
    manifest, manifest_bytes = _read_json(root, EVENT_MANIFEST)
    events, events_bytes = _read_json(root, EVENTS)
    panel, panel_bytes = _read_json(root, COMMON_PANEL)
    contents = {
        EVENT_MANIFEST: manifest_bytes,
        EVENTS: events_bytes,
        COMMON_PANEL: panel_bytes,
        OUTCOME_CONTRACT: _read_bytes(root, OUTCOME_CONTRACT),
        EVENT_CONTRACT: _read_bytes(root, EVENT_CONTRACT),
        STATE_MACHINE_CONTRACT: _read_bytes(root, STATE_MACHINE_CONTRACT),
    }
    for relative, content in contents.items():
        _validate_identity(relative, content)
    _validate_event_manifest(manifest, contents)
    dates, close_by_member = _validate_common_panel(panel)
    _validate_events_dataset(events, dates)
    _require(events.get("source_common_panel_path") == COMMON_PANEL.as_posix(), "event panel path mismatch")
    _require(events.get("source_common_panel_sha256") == sha256_bytes(panel_bytes), "event panel hash mismatch")
    _require(events.get("source_event_contract_sha256") == sha256_bytes(contents[EVENT_CONTRACT]), "event contract chain mismatch")
    return {
        "events": events["events"],
        "dates": dates,
        "close_by_member": close_by_member,
        "source_files": {
            "event_manifest": _source_record(EVENT_MANIFEST, manifest_bytes),
            "events": _source_record(EVENTS, events_bytes),
            "common_panel": _source_record(COMMON_PANEL, panel_bytes),
        },
        "source_contracts": {
            "STRATEGY_STYLE_FORWARD_OUTCOME_WALK_FORWARD_PREREGISTRATION_V1": _source_record(OUTCOME_CONTRACT, contents[OUTCOME_CONTRACT]),
            "STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1": _source_record(EVENT_CONTRACT, contents[EVENT_CONTRACT]),
            "STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1": _source_record(STATE_MACHINE_CONTRACT, contents[STATE_MACHINE_CONTRACT]),
        },
    }


def _median(values: Iterable[float]) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _direction(value: float) -> str:
    if value > 0:
        return "POSITIVE"
    if value < 0:
        return "NEGATIVE"
    return "FLAT"


def _partition(start_date: str) -> tuple[str, str | None]:
    if "2013-01-04" <= start_date <= "2017-12-31":
        return "DEVELOPMENT_EXCLUDED", None
    if "2018-01-01" <= start_date <= "2025-12-31":
        return "FORMAL_OOS", f"WF_{start_date[:4]}"
    if "2026-01-01" <= start_date <= AS_OF:
        return "PROSPECTIVE_NOT_SCORED", None
    raise StrategyStyleWalkForwardError(f"event date outside frozen partitions: {start_date}")


def _style_period_returns(
    start: int,
    end: int,
    close_by_member: dict[str, list[float]],
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    member_returns: dict[str, dict[str, float]] = {}
    style_returns: dict[str, float] = {}
    for style in STYLE_ORDER:
        values = {
            member: close_by_member[member][end] / close_by_member[member][start] - 1
            for member in STYLE_MEMBERS[style]
        }
        member_returns[style] = values
        style_returns[style] = sum(values.values()) / len(values)
    return member_returns, style_returns


def _null_period(status: str) -> dict[str, Any]:
    _require(status in {"UNAVAILABLE_AS_OF", "NOT_CLOSED"}, "invalid null period status")
    return {
        "availability_status": status,
        "evaluation_end_index": None,
        "evaluation_end_date": None,
        "member_total_returns": None,
        "style_total_return": None,
        "peer_style_total_returns": None,
        "peer_benchmark_total_return": None,
        "peer_relative_return": None,
    }


def _available_period(
    style: str,
    start: int,
    end: int,
    dates: list[str],
    close_by_member: dict[str, list[float]],
) -> dict[str, Any]:
    _require(0 <= start < end < DATE_COUNT, "invalid available period")
    member_returns, style_returns = _style_period_returns(start, end, close_by_member)
    peers = {peer: style_returns[peer] for peer in STYLE_ORDER if peer != style}
    peer_benchmark = sum(peers.values()) / len(peers)
    style_return = style_returns[style]
    return {
        "availability_status": "AVAILABLE",
        "evaluation_end_index": end,
        "evaluation_end_date": dates[end],
        "member_total_returns": member_returns[style],
        "style_total_return": style_return,
        "peer_style_total_returns": peers,
        "peer_benchmark_total_return": peer_benchmark,
        "peer_relative_return": style_return - peer_benchmark,
    }


def build_event_outcomes(validated: dict[str, Any]) -> dict[str, Any]:
    dates = validated["dates"]
    close_by_member = validated["close_by_member"]
    outcomes: list[dict[str, Any]] = []
    for event in validated["events"]:
        start_index = event["event_start_index"] + 1
        start_date = dates[start_index] if start_index < DATE_COUNT else None
        partition, fold_id = _partition(event["event_start_observation_date"])
        periods: dict[str, dict[str, Any]] = {}
        for horizon in HORIZON_ORDER:
            end_index = start_index + HORIZON_LENGTHS[horizon]
            if start_index < DATE_COUNT and end_index < DATE_COUNT:
                periods[horizon] = _available_period(
                    event["style_unit"], start_index, end_index, dates, close_by_member
                )
            else:
                periods[horizon] = _null_period("UNAVAILABLE_AS_OF")
        if event["event_status"] == "OPEN":
            episode = _null_period("NOT_CLOSED")
        else:
            episode_end = event["event_end_index"] + 1
            if start_index < DATE_COUNT and episode_end < DATE_COUNT and start_index < episode_end:
                episode = _available_period(
                    event["style_unit"], start_index, episode_end, dates, close_by_member
                )
            else:
                episode = _null_period("UNAVAILABLE_AS_OF")
        outcome = {
            "event_id": event["event_id"],
            "profile_id": event["profile_id"],
            "style_unit": event["style_unit"],
            "event_status": event["event_status"],
            "event_start_observation_date": event["event_start_observation_date"],
            "evaluation_start_index": start_index,
            "evaluation_start_date": start_date,
            "walk_forward_partition": partition,
            "walk_forward_fold_id": fold_id,
            "H20": periods["H20"],
            "H60": periods["H60"],
            "H120": periods["H120"],
            "episode": episode,
        }
        _require(set(outcome) == OUTCOME_FIELDS, "outcome field inventory mismatch")
        _require(all(set(outcome[key]) == PERIOD_FIELDS for key in (*HORIZON_ORDER, "episode")), "period field inventory mismatch")
        outcomes.append(outcome)
    sources = validated["source_files"]
    contracts = validated["source_contracts"]
    return {
        "schema_version": "1.0",
        "dataset_id": "STRATEGY_STYLE_EVENT_OUTCOMES_V1",
        "source_as_of_date": AS_OF,
        "source_events_manifest_path": EVENT_MANIFEST.as_posix(),
        "source_events_manifest_sha256": sources["event_manifest"]["sha256"],
        "source_events_path": EVENTS.as_posix(),
        "source_events_sha256": sources["events"]["sha256"],
        "source_common_panel_path": COMMON_PANEL.as_posix(),
        "source_common_panel_sha256": sources["common_panel"]["sha256"],
        "source_outcome_contract_sha256": contracts[
            "STRATEGY_STYLE_FORWARD_OUTCOME_WALK_FORWARD_PREREGISTRATION_V1"
        ]["sha256"],
        "event_count": len(outcomes),
        "horizon_order": list(HORIZON_ORDER),
        "partition_values": list(PARTITION_VALUES),
        "formal_fold_order": list(FORMAL_FOLD_ORDER),
        "availability_values": list(AVAILABILITY_VALUES),
        "outcomes": outcomes,
    }


def _count_directions(values: Iterable[float]) -> tuple[int, int, int]:
    directions = [_direction(value) for value in values]
    return (
        directions.count("POSITIVE"),
        directions.count("FLAT"),
        directions.count("NEGATIVE"),
    )


def _build_first_layer(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile_id in PROFILE_ORDER:
        for style in STYLE_ORDER:
            for fold_id in FORMAL_FOLD_ORDER:
                matching = [
                    row
                    for row in outcomes
                    if row["profile_id"] == profile_id
                    and row["style_unit"] == style
                    and row["walk_forward_partition"] == "FORMAL_OOS"
                    and row["walk_forward_fold_id"] == fold_id
                ]
                for horizon in HORIZON_ORDER:
                    available = [row[horizon] for row in matching if row[horizon]["availability_status"] == "AVAILABLE"]
                    unavailable_count = len(matching) - len(available)
                    relative = [row["peer_relative_return"] for row in available]
                    style_returns = [row["style_total_return"] for row in available]
                    positive, flat, negative = _count_directions(relative)
                    if available:
                        summary_status = "AVAILABLE"
                        positive_rate = positive / len(available)
                    else:
                        summary_status = "NO_ELIGIBLE_EVENTS"
                        positive_rate = None
                    rows.append(
                        {
                            "profile_id": profile_id,
                            "style_unit": style,
                            "walk_forward_fold_id": fold_id,
                            "horizon": horizon,
                            "summary_status": summary_status,
                            "eligible_event_count": len(available),
                            "unavailable_event_count": unavailable_count,
                            "median_style_total_return": _median(style_returns),
                            "median_peer_relative_return": _median(relative),
                            "positive_count": positive,
                            "flat_count": flat,
                            "negative_count": negative,
                            "positive_rate": positive_rate,
                        }
                    )
    return rows


def _build_second_layer(first: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile_id in PROFILE_ORDER:
        for style in STYLE_ORDER:
            for horizon in HORIZON_ORDER:
                available = [
                    row
                    for row in first
                    if row["profile_id"] == profile_id
                    and row["style_unit"] == style
                    and row["horizon"] == horizon
                    and row["summary_status"] == "AVAILABLE"
                ]
                values = [row["median_peer_relative_return"] for row in available]
                positive, flat, negative = _count_directions(values)
                rows.append(
                    {
                        "profile_id": profile_id,
                        "style_unit": style,
                        "horizon": horizon,
                        "available_fold_count": len(available),
                        "positive_fold_count": positive,
                        "flat_fold_count": flat,
                        "negative_fold_count": negative,
                        "median_of_fold_median_peer_relative_return": _median(values),
                    }
                )
    return rows


def _build_third_layer(first: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile_id in PROFILE_ORDER:
        for fold_id in FORMAL_FOLD_ORDER:
            for horizon in HORIZON_ORDER:
                available = [
                    row
                    for row in first
                    if row["profile_id"] == profile_id
                    and row["walk_forward_fold_id"] == fold_id
                    and row["horizon"] == horizon
                    and row["summary_status"] == "AVAILABLE"
                ]
                values = [row["median_peer_relative_return"] for row in available]
                rows.append(
                    {
                        "profile_id": profile_id,
                        "walk_forward_fold_id": fold_id,
                        "horizon": horizon,
                        "summary_status": "AVAILABLE" if available else "NO_ELIGIBLE_EVENTS",
                        "available_style_count": len(available),
                        "profile_fold_median_peer_relative_return": _median(values),
                    }
                )
    return rows


def _build_fourth_layer(third: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile_id in PROFILE_ORDER:
        for horizon in HORIZON_ORDER:
            available = [
                row
                for row in third
                if row["profile_id"] == profile_id
                and row["horizon"] == horizon
                and row["summary_status"] == "AVAILABLE"
            ]
            values = [row["profile_fold_median_peer_relative_return"] for row in available]
            positive, flat, negative = _count_directions(values)
            rows.append(
                {
                    "profile_id": profile_id,
                    "horizon": horizon,
                    "available_fold_count": len(available),
                    "positive_fold_count": positive,
                    "flat_fold_count": flat,
                    "negative_fold_count": negative,
                    "median_of_profile_fold_medians": _median(values),
                }
            )
    return rows


def _build_episode_summary(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile_id in PROFILE_ORDER:
        for style in STYLE_ORDER:
            matching = [
                row
                for row in outcomes
                if row["profile_id"] == profile_id
                and row["style_unit"] == style
                and row["walk_forward_partition"] == "FORMAL_OOS"
            ]
            available = [row["episode"] for row in matching if row["episode"]["availability_status"] == "AVAILABLE"]
            values = [row["peer_relative_return"] for row in available]
            positive, flat, negative = _count_directions(values)
            rows.append(
                {
                    "profile_id": profile_id,
                    "style_unit": style,
                    "closed_available_episode_count": len(available),
                    "episode_median_peer_relative_return": _median(values),
                    "episode_positive_count": positive,
                    "episode_flat_count": flat,
                    "episode_negative_count": negative,
                    "open_count": sum(row["episode"]["availability_status"] == "NOT_CLOSED" for row in matching),
                    "episode_unavailable_as_of_count": sum(row["episode"]["availability_status"] == "UNAVAILABLE_AS_OF" for row in matching),
                }
            )
    return rows


def _lookup(rows: list[dict[str, Any]], **criteria: Any) -> dict[str, Any]:
    matches = [row for row in rows if all(row.get(key) == value for key, value in criteria.items())]
    _require(len(matches) == 1, f"summary lookup mismatch: {criteria}")
    return matches[0]


def _build_profile_decisions(
    second: list[dict[str, Any]],
    fourth: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for profile_id in PROFILE_ORDER:
        h60_style_rows = [
            _lookup(second, profile_id=profile_id, style_unit=style, horizon="H60")
            for style in STYLE_ORDER
        ]
        h20 = _lookup(fourth, profile_id=profile_id, horizon="H20")
        h60 = _lookup(fourth, profile_id=profile_id, horizon="H60")
        h120 = _lookup(fourth, profile_id=profile_id, horizon="H120")
        positive_style_count = sum(
            row["available_fold_count"] >= MINIMUM_AVAILABLE_FOLD_COUNT
            and row["median_of_fold_median_peer_relative_return"] is not None
            and row["median_of_fold_median_peer_relative_return"] > 0
            for row in h60_style_rows
        )
        condition_a = positive_style_count >= 3
        condition_b = h60["positive_fold_count"] >= 5
        condition_c = (
            h60["available_fold_count"] >= MINIMUM_AVAILABLE_FOLD_COUNT
            and h60["median_of_profile_fold_medians"] is not None
            and h60["median_of_profile_fold_medians"] > 0
        )

        def secondary_pass(row: dict[str, Any]) -> bool:
            return (
                row["available_fold_count"] >= MINIMUM_AVAILABLE_FOLD_COUNT
                and row["median_of_profile_fold_medians"] is not None
                and row["median_of_profile_fold_medians"] > 0
            )

        h20_passed = secondary_pass(h20)
        h120_passed = secondary_pass(h120)
        condition_d = h20_passed or h120_passed
        support = "WALK_FORWARD_SUPPORTED" if all((condition_a, condition_b, condition_c, condition_d)) else "NOT_SUPPORTED"
        decisions.append(
            {
                "profile_id": profile_id,
                "condition_a_positive_style_count": positive_style_count,
                "condition_a_passed": condition_a,
                "condition_b_positive_fold_count": h60["positive_fold_count"],
                "condition_b_passed": condition_b,
                "condition_c_available_fold_count": h60["available_fold_count"],
                "condition_c_median": h60["median_of_profile_fold_medians"],
                "condition_c_passed": condition_c,
                "condition_d_h20_available_fold_count": h20["available_fold_count"],
                "condition_d_h20_median": h20["median_of_profile_fold_medians"],
                "condition_d_h20_passed": h20_passed,
                "condition_d_h120_available_fold_count": h120["available_fold_count"],
                "condition_d_h120_median": h120["median_of_profile_fold_medians"],
                "condition_d_h120_passed": h120_passed,
                "condition_d_passed": condition_d,
                "h60_positive_fold_count": h60["positive_fold_count"],
                "h60_positive_style_count": positive_style_count,
                "profile_support_status": support,
            }
        )
    return decisions


def select_profile(
    decisions: list[dict[str, Any]],
    fourth: list[dict[str, Any]],
) -> tuple[list[str], str, str | None]:
    supported = [row["profile_id"] for row in decisions if row["profile_support_status"] == "WALK_FORWARD_SUPPORTED"]
    if not supported:
        return supported, "REJECTED", None
    if len(supported) == 1:
        return supported, "SUPPORTED", supported[0]
    decision_by_profile = {row["profile_id"]: row for row in decisions}
    h60_by_profile = {
        profile_id: _lookup(fourth, profile_id=profile_id, horizon="H60")
        for profile_id in supported
    }
    h120_by_profile = {
        profile_id: _lookup(fourth, profile_id=profile_id, horizon="H120")
        for profile_id in supported
    }
    remaining = list(supported)

    def retain_max(value_by_profile: dict[str, float | int]) -> None:
        nonlocal remaining
        best = max(value_by_profile[profile_id] for profile_id in remaining)
        remaining = [profile_id for profile_id in remaining if value_by_profile[profile_id] == best]

    retain_max({profile_id: decision_by_profile[profile_id]["h60_positive_fold_count"] for profile_id in supported})
    if len(remaining) > 1:
        retain_max({profile_id: decision_by_profile[profile_id]["h60_positive_style_count"] for profile_id in supported})
    if len(remaining) > 1:
        retain_max({profile_id: h60_by_profile[profile_id]["median_of_profile_fold_medians"] for profile_id in supported})
    if len(remaining) > 1:
        valid = [
            profile_id
            for profile_id in remaining
            if h120_by_profile[profile_id]["available_fold_count"] >= MINIMUM_AVAILABLE_FOLD_COUNT
            and h120_by_profile[profile_id]["median_of_profile_fold_medians"] is not None
        ]
        if valid:
            remaining = valid
            if len(remaining) > 1:
                retain_max({profile_id: h120_by_profile[profile_id]["median_of_profile_fold_medians"] for profile_id in supported})
    if len(remaining) == 1:
        return supported, "SUPPORTED", remaining[0]
    return supported, "AMBIGUOUS", None


def build_walk_forward_summary(event_outcomes: dict[str, Any]) -> dict[str, Any]:
    outcomes = event_outcomes["outcomes"]
    first = _build_first_layer(outcomes)
    second = _build_second_layer(first)
    third = _build_third_layer(first)
    fourth = _build_fourth_layer(third)
    episodes = _build_episode_summary(outcomes)
    decisions = _build_profile_decisions(second, fourth)
    supported, mechanism_decision, selected_profile = select_profile(decisions, fourth)
    return {
        "schema_version": "1.0",
        "dataset_id": "STRATEGY_STYLE_WALK_FORWARD_SUMMARY_V1",
        "source_as_of_date": AS_OF,
        "source_event_outcomes_path": f"{OUTPUT_DIR.as_posix()}/event_outcomes.json",
        "source_event_outcomes_sha256": "",
        "profile_order": list(PROFILE_ORDER),
        "style_order": list(STYLE_ORDER),
        "horizon_order": list(HORIZON_ORDER),
        "formal_fold_order": list(FORMAL_FOLD_ORDER),
        "minimum_available_fold_count": MINIMUM_AVAILABLE_FOLD_COUNT,
        "profile_style_fold_horizon": first,
        "profile_style_horizon": second,
        "profile_fold_horizon": third,
        "profile_horizon": fourth,
        "episode_profile_style": episodes,
        "profile_decisions": decisions,
        "supported_profiles": supported,
        "mechanism_decision": mechanism_decision,
        "selected_profile": selected_profile,
    }


def _validate_outputs(
    event_outcomes: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    outcomes = event_outcomes["outcomes"]
    _require(event_outcomes["event_count"] == EVENT_COUNT == len(outcomes), "outcome count mismatch")
    _require(all(set(row) == OUTCOME_FIELDS for row in outcomes), "outcome fields mismatch")
    _require(all(set(row[key]) == PERIOD_FIELDS for row in outcomes for key in (*HORIZON_ORDER, "episode")), "period fields mismatch")
    _require([row["event_id"] for row in outcomes] == [row["event_id"] for row in event_outcomes["outcomes"]], "outcome order mismatch")
    _require(len(summary["profile_style_fold_horizon"]) == 288, "first-layer row count mismatch")
    _require(len(summary["profile_style_horizon"]) == 36, "second-layer row count mismatch")
    _require(len(summary["profile_fold_horizon"]) == 72, "third-layer row count mismatch")
    _require(len(summary["profile_horizon"]) == 9, "fourth-layer row count mismatch")
    _require(len(summary["episode_profile_style"]) == 12, "episode row count mismatch")
    _require(len(summary["profile_decisions"]) == 3, "profile decision count mismatch")
    _require(summary["mechanism_decision"] in MECHANISM_DECISIONS, "mechanism decision mismatch")
    _require(summary["supported_profiles"] == [profile for profile in PROFILE_ORDER if profile in summary["supported_profiles"]], "supported profile order mismatch")
    if summary["mechanism_decision"] == "SUPPORTED":
        _require(summary["selected_profile"] in summary["supported_profiles"], "selected profile mismatch")
    else:
        _require(summary["selected_profile"] is None, "non-supported decision must not select profile")


def build_artifact_bytes(root: Path, as_of: str) -> dict[str, bytes]:
    validated = load_and_validate_inputs(root, as_of)
    event_outcomes = build_event_outcomes(validated)
    event_outcomes_content = json_bytes(event_outcomes)
    summary = build_walk_forward_summary(event_outcomes)
    summary["source_event_outcomes_sha256"] = sha256_bytes(event_outcomes_content)
    _validate_outputs(event_outcomes, summary)
    summary_content = json_bytes(summary)
    manifest = {
        "schema_version": "1.0",
        "artifact_set_id": "STRATEGY_STYLE_WALK_FORWARD_ARTIFACT_V1",
        "source_as_of_date": AS_OF,
        "source_files": validated["source_files"],
        "source_contracts": validated["source_contracts"],
        "outputs": {
            "event_outcomes": {
                "path": f"{OUTPUT_DIR.as_posix()}/event_outcomes.json",
                "sha256": sha256_bytes(event_outcomes_content),
                "bytes": len(event_outcomes_content),
            },
            "walk_forward_summary": {
                "path": f"{OUTPUT_DIR.as_posix()}/walk_forward_summary.json",
                "sha256": sha256_bytes(summary_content),
                "bytes": len(summary_content),
            },
        },
        "invariants": {
            "date_count": DATE_COUNT,
            "event_count": EVENT_COUNT,
            "profile_count": 3,
            "style_count": 4,
            "formal_fold_count": 8,
            "horizon_count": 3,
            "minimum_available_fold_count": MINIMUM_AVAILABLE_FOLD_COUNT,
            "offline_only": True,
            "no_parameter_refit": True,
            "no_portfolio_simulation": True,
        },
        "statuses": {
            "forward_outcome_implementation_status": "IMPLEMENTED",
            "forward_outcome_dataset_status": "BUILT",
            "walk_forward_status": "RUN",
            "profile_selection_execution_status": "RUN",
            "allocation_status": "NOT_DEFINED",
            "backtest_status": "NOT_RUN",
            "integration_status": "DO_NOT_INTEGRATE",
        },
        "mechanism_decision": summary["mechanism_decision"],
        "selected_profile": summary["selected_profile"],
    }
    artifacts = {
        "manifest.json": json_bytes(manifest),
        "event_outcomes.json": event_outcomes_content,
        "walk_forward_summary.json": summary_content,
    }
    validate_artifact_bytes(artifacts)
    return artifacts


def validate_artifact_bytes(artifacts: dict[str, bytes]) -> None:
    _require(set(artifacts) == {"manifest.json", "event_outcomes.json", "walk_forward_summary.json"}, "artifact inventory mismatch")
    manifest = json.loads(artifacts["manifest.json"])
    outcomes = json.loads(artifacts["event_outcomes.json"])
    summary = json.loads(artifacts["walk_forward_summary.json"])
    for key, name in (("event_outcomes", "event_outcomes.json"), ("walk_forward_summary", "walk_forward_summary.json")):
        record = manifest["outputs"][key]
        _require(record["sha256"] == sha256_bytes(artifacts[name]), f"output hash mismatch: {name}")
        _require(record["bytes"] == len(artifacts[name]), f"output bytes mismatch: {name}")
    _require(summary["source_event_outcomes_sha256"] == sha256_bytes(artifacts["event_outcomes.json"]), "summary outcome hash mismatch")
    _require(manifest["mechanism_decision"] == summary["mechanism_decision"], "manifest decision mismatch")
    _require(manifest["selected_profile"] == summary["selected_profile"], "manifest selection mismatch")
    _validate_outputs(outcomes, summary)
    forbidden = (
        "entry_price", "exit_price", "execution_date", "trade_date", "position",
        "weight", "allocation", "capital", "transaction_cost", "portfolio_return",
        "equity_curve", "maximum_drawdown", "Sharpe", "Calmar", "win_rate",
        "success_rate", "best_profile", "profile_rank", "style_rank",
    )
    text = artifacts["event_outcomes.json"].decode("utf-8") + artifacts["walk_forward_summary.json"].decode("utf-8")
    _require(not any(term in text for term in forbidden), "artifacts contain forbidden fields")


def publish_artifacts(root: Path, artifacts: dict[str, bytes]) -> None:
    target = root / OUTPUT_DIR
    target.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".strategy-style-walk-forward-", dir=target.parent))
    staged = staging_root / "complete"
    backup = staging_root / "previous"
    try:
        staged.mkdir()
        for name, content in artifacts.items():
            (staged / name).write_bytes(content)
        staged_artifacts = {
            path.name: path.read_bytes()
            for path in staged.iterdir()
            if path.is_file()
        }
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


def build_strategy_style_walk_forward(
    root: Path,
    as_of: str,
    *,
    publish: bool = True,
) -> dict[str, bytes]:
    artifacts = build_artifact_bytes(root, as_of)
    if publish:
        publish_artifacts(root, artifacts)
    return artifacts


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic strategy-style walk-forward outcomes."
    )
    parser.add_argument("--as-of", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        artifacts = build_strategy_style_walk_forward(ROOT, args.as_of)
    except (OSError, StrategyStyleWalkForwardError) as exc:
        print(f"strategy-style walk-forward build failed: {exc}")
        return 1
    manifest = json.loads(artifacts["manifest.json"])
    print(
        f"{OUTPUT_DIR.as_posix()}: {manifest['mechanism_decision']} "
        f"selected_profile={manifest['selected_profile']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
