"""Apply the frozen strategy-style daily logic state machine offline."""

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
SOURCE_DIR = Path("data/strategy_style_category_calculations_v1")
SOURCE_MANIFEST = SOURCE_DIR / "manifest.json"
COMMON_PANEL = SOURCE_DIR / "common_panel.json"
CATEGORY_STATES = SOURCE_DIR / "category_states.json"
STATE_MACHINE_CONTRACT = Path(
    "docs/STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md"
)
UPSTREAM_CONTRACTS = {
    "STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1": Path(
        "docs/STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1.md"
    ),
    "STRATEGY_STYLE_OBSERVATION_DATA_CONTRACT_V1": Path(
        "docs/STRATEGY_STYLE_OBSERVATION_DATA_CONTRACT_V1.md"
    ),
    "STRATEGY_STYLE_SIGNAL_CATEGORY_PREREGISTRATION_V1": Path(
        "docs/STRATEGY_STYLE_SIGNAL_CATEGORY_PREREGISTRATION_V1.md"
    ),
    "STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1": STATE_MACHINE_CONTRACT,
    "STRATEGY_STYLE_CATEGORY_CALCULATION_PREREGISTRATION_V1": Path(
        "docs/STRATEGY_STYLE_CATEGORY_CALCULATION_PREREGISTRATION_V1.md"
    ),
}
OUTPUT_DIR = Path("data/strategy_style_daily_logic_v1")
PROFILE_ORDER = ("PROFILE_A", "PROFILE_B", "PROFILE_C")
STYLE_ORDER = ("growth", "value", "dividend", "cash_flow")
STYLE_MEMBERS = {
    "growth": ["CN2296.CNI"],
    "value": ["CN2371.CNI"],
    "dividend": ["H00015.CSI", "H00922.CSI"],
    "cash_flow": ["480092.CNI"],
}
CATEGORIES = (
    "drawdown_pressure",
    "absolute_stabilization",
    "relative_stabilization",
    "adverse_continuation",
)
LOGICAL_STATES = ("INACTIVE", "ACTIVE")
DAILY_RESULTS = (
    "BLOCKED",
    "NO_CHANGE",
    "ENTRY_CANDIDATE",
    "HOLD_CANDIDATE",
    "EXIT_CANDIDATE",
)
COMMON_STATES = {"MET", "NOT_MET", "UNAVAILABLE"}
AGREEMENT_STATES = {"AGREEMENT", "CONFLICT", "UNAVAILABLE"}
DATE_COUNT = 3284


class StrategyStyleDailyLogicError(RuntimeError):
    """Raised when an input or output violates the frozen daily-logic contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StrategyStyleDailyLogicError(message)


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
        raise StrategyStyleDailyLogicError(f"cannot read formal input: {relative}") from exc


def _read_json(root: Path, relative: Path) -> tuple[dict[str, Any], bytes]:
    content = _read_bytes(root, relative)
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StrategyStyleDailyLogicError(f"invalid JSON input: {relative}") from exc
    _require(isinstance(value, dict), f"formal input must be an object: {relative}")
    return value, content


def _source_record(relative: Path, content: bytes) -> dict[str, Any]:
    return {
        "path": relative.as_posix(),
        "sha256": sha256_bytes(content),
        "bytes": len(content),
    }


def load_and_validate_inputs(root: Path, as_of: str) -> dict[str, Any]:
    """Validate the complete permitted source chain without reading raw prices."""
    _require(as_of == AS_OF, f"--as-of must be {AS_OF}")
    manifest, manifest_bytes = _read_json(root, SOURCE_MANIFEST)
    panel, panel_bytes = _read_json(root, COMMON_PANEL)
    states, states_bytes = _read_json(root, CATEGORY_STATES)
    contract_bytes = _read_bytes(root, STATE_MACHINE_CONTRACT)

    _require(
        manifest.get("artifact_set_id")
        == "STRATEGY_STYLE_CATEGORY_CALCULATIONS_V1",
        "source artifact set id mismatch",
    )
    _require(manifest.get("source_as_of_date") == as_of, "source as-of mismatch")
    expected_statuses = {
        "common_panel_status": "BUILT",
        "category_calculation_implementation_status": "IMPLEMENTED",
        "parameter_selection_status": "NOT_RUN",
        "entry_exit_state_machine_status": "NOT_APPLIED",
        "event_status": "NOT_BUILT",
        "walk_forward_status": "NOT_RUN",
        "integration_status": "DO_NOT_INTEGRATE",
    }
    source_statuses = manifest.get("statuses", {})
    for key, expected in expected_statuses.items():
        _require(source_statuses.get(key) == expected, f"source status mismatch: {key}")

    outputs = manifest.get("outputs", {})
    for key, relative, content in (
        ("common_panel", COMMON_PANEL, panel_bytes),
        ("category_states", CATEGORY_STATES, states_bytes),
    ):
        record = outputs.get(key, {})
        _require(record.get("path") == relative.as_posix(), f"source output path mismatch: {key}")
        _require(record.get("sha256") == sha256_bytes(content), f"source output hash mismatch: {key}")
        _require(record.get("bytes") == len(content), f"source output byte count mismatch: {key}")

    _require(panel.get("dataset_id") == "STRATEGY_STYLE_COMMON_PANEL_V1", "common panel dataset id mismatch")
    _require(panel.get("source_as_of_date") == as_of, "common panel as-of mismatch")
    dates = panel.get("dates")
    _require(isinstance(dates, list), "common panel dates must be an array")
    _require(len(dates) == DATE_COUNT, "common panel date count mismatch")
    _require(dates[0] == "2013-01-04" and dates[-1] == as_of, "common panel date bounds mismatch")
    _require(dates == sorted(set(dates)), "common panel dates must be sorted and unique")
    _require(all(date <= as_of for date in dates), "common panel contains future date")
    _require(panel.get("member_count") == 5, "common panel member count mismatch")
    _require(panel.get("style_unit_count") == 4, "common panel style count mismatch")
    _require(panel.get("member_date_observation_count") == 16420, "common panel observation count mismatch")

    _require(states.get("dataset_id") == "STRATEGY_STYLE_CATEGORY_STATES_V1", "category states dataset id mismatch")
    _require(states.get("date_count") == DATE_COUNT, "category states date count mismatch")
    _require(states.get("date_axis") == "common_panel.dates", "category states date axis mismatch")
    _require(states.get("profile_order") == list(PROFILE_ORDER), "profile order mismatch")
    _require(states.get("source_common_panel_path") == COMMON_PANEL.as_posix(), "category states panel path mismatch")
    _require(states.get("source_common_panel_sha256") == sha256_bytes(panel_bytes), "category states panel hash mismatch")
    calculation_contract = manifest.get("source_contracts", {}).get(
        "STRATEGY_STYLE_CATEGORY_CALCULATION_PREREGISTRATION_V1", {}
    )
    _require(
        states.get("source_calculation_contract_sha256")
        == calculation_contract.get("sha256"),
        "calculation contract hash mismatch",
    )
    state_contract_record = manifest.get("source_contracts", {}).get(
        "STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1", {}
    )
    _require(
        state_contract_record.get("path") == STATE_MACHINE_CONTRACT.as_posix(),
        "state-machine contract path mismatch",
    )
    _require(
        state_contract_record.get("sha256") == sha256_bytes(contract_bytes),
        "state-machine contract hash mismatch",
    )
    _require(
        state_contract_record.get("bytes") == len(contract_bytes),
        "state-machine contract byte count mismatch",
    )
    source_contracts = manifest.get("source_contracts", {})
    _require(set(source_contracts) == set(UPSTREAM_CONTRACTS), "upstream contract inventory mismatch")
    for name, relative in UPSTREAM_CONTRACTS.items():
        contract = source_contracts[name]
        _require(contract.get("path") == relative.as_posix(), f"upstream contract path mismatch: {name}")
        content = _read_bytes(root, relative)
        _require(contract.get("sha256") == sha256_bytes(content), f"upstream contract hash mismatch: {relative}")
        _require(contract.get("bytes") == len(content), f"upstream contract byte count mismatch: {relative}")

    profiles = states.get("profiles")
    _require(isinstance(profiles, list), "category profiles must be an array")
    _require([profile.get("profile_id") for profile in profiles] == list(PROFILE_ORDER), "category profile order mismatch")
    for profile in profiles:
        styles = profile.get("style_states")
        _require(isinstance(styles, list), "style states must be an array")
        _require([style.get("style_unit") for style in styles] == list(STYLE_ORDER), "style order mismatch")
        for style, expected_style in zip(styles, STYLE_ORDER, strict=True):
            _require(style.get("member_asset_ids") == STYLE_MEMBERS[expected_style], f"style member map mismatch: {expected_style}")
            category_arrays = style.get("states")
            _require(isinstance(category_arrays, dict), f"style category states missing: {expected_style}")
            _require(set(category_arrays) == set(CATEGORIES), f"style category set mismatch: {expected_style}")
            for category in CATEGORIES:
                values = category_arrays[category]
                _require(isinstance(values, list) and len(values) == DATE_COUNT, f"category array length mismatch: {expected_style}/{category}")
                _require(set(values) <= COMMON_STATES, f"invalid category state: {expected_style}/{category}")
            if expected_style == "dividend":
                agreement = style.get("dividend_member_agreement")
                _require(isinstance(agreement, list) and len(agreement) == DATE_COUNT, "dividend agreement length mismatch")
                _require(set(agreement) <= AGREEMENT_STATES, "invalid dividend agreement state")
            else:
                _require("dividend_member_agreement" not in style, f"unexpected agreement field: {expected_style}")

    return {
        "manifest": manifest,
        "panel": panel,
        "states": states,
        "source_files": {
            "category_calculation_manifest": _source_record(SOURCE_MANIFEST, manifest_bytes),
            "common_panel": _source_record(COMMON_PANEL, panel_bytes),
            "category_states": _source_record(CATEGORY_STATES, states_bytes),
        },
        "state_machine_contract": _source_record(STATE_MACHINE_CONTRACT, contract_bytes),
    }


def evaluate_day(
    style: str,
    state_before: str,
    category_states: dict[str, str],
    agreement: str | None = None,
) -> tuple[str, str]:
    """Evaluate one style/day and return daily result and next logical state."""
    _require(style in STYLE_ORDER, f"invalid style: {style}")
    _require(state_before in LOGICAL_STATES, f"invalid logical state: {state_before}")
    _require(set(category_states) == set(CATEGORIES), "daily category set mismatch")
    _require(set(category_states.values()) <= COMMON_STATES, "invalid daily category state")
    if style == "dividend":
        _require(agreement in AGREEMENT_STATES, "invalid dividend agreement")
    else:
        _require(agreement is None, f"unexpected agreement for {style}")

    if "UNAVAILABLE" in category_states.values() or (
        style == "dividend" and agreement == "UNAVAILABLE"
    ):
        return "BLOCKED", state_before

    pressure = category_states["drawdown_pressure"]
    absolute = category_states["absolute_stabilization"]
    relative = category_states["relative_stabilization"]
    adverse = category_states["adverse_continuation"]

    if state_before == "ACTIVE":
        should_exit = (
            adverse == "MET"
            or pressure == "NOT_MET"
            or (absolute == "NOT_MET" and relative == "NOT_MET")
            or (style == "dividend" and agreement == "CONFLICT")
        )
        return ("EXIT_CANDIDATE", "INACTIVE") if should_exit else (
            "HOLD_CANDIDATE",
            "ACTIVE",
        )

    stabilization_met = absolute == "MET" or relative == "MET"
    if style == "growth":
        should_enter = (
            pressure == "MET"
            and absolute == "MET"
            and relative == "MET"
            and adverse == "NOT_MET"
        )
    else:
        should_enter = (
            pressure == "MET"
            and adverse == "NOT_MET"
            and stabilization_met
            and (style != "dividend" or agreement == "AGREEMENT")
        )
    return ("ENTRY_CANDIDATE", "ACTIVE") if should_enter else (
        "NO_CHANGE",
        "INACTIVE",
    )


def build_style_logic(style: str, source_style: dict[str, Any]) -> dict[str, Any]:
    state_before_values: list[str] = []
    results: list[str] = []
    state_after_values: list[str] = []
    current_state = "INACTIVE"
    category_arrays = source_style["states"]
    agreement_array = source_style.get("dividend_member_agreement")
    for index in range(DATE_COUNT):
        daily_categories = {
            category: category_arrays[category][index] for category in CATEGORIES
        }
        agreement = agreement_array[index] if agreement_array is not None else None
        result, state_after = evaluate_day(
            style, current_state, daily_categories, agreement
        )
        state_before_values.append(current_state)
        results.append(result)
        state_after_values.append(state_after)
        current_state = state_after
    return {
        "style_unit": style,
        "member_asset_ids": STYLE_MEMBERS[style],
        "state_before": state_before_values,
        "daily_result": results,
        "state_after": state_after_values,
    }


def build_daily_logic(validated: dict[str, Any]) -> dict[str, Any]:
    output_profiles: list[dict[str, Any]] = []
    for source_profile in validated["states"]["profiles"]:
        style_logic = [
            build_style_logic(style, source_style)
            for style, source_style in zip(
                STYLE_ORDER, source_profile["style_states"], strict=True
            )
        ]
        concurrent_sets = [
            [
                style_record["style_unit"]
                for style_record in style_logic
                if style_record["daily_result"][index] == "ENTRY_CANDIDATE"
            ]
            for index in range(DATE_COUNT)
        ]
        output_profiles.append(
            {
                "profile_id": source_profile["profile_id"],
                "style_logic": style_logic,
                "concurrent_entry_candidate_set": concurrent_sets,
            }
        )
    source_files = validated["source_files"]
    return {
        "schema_version": "1.0",
        "dataset_id": "STRATEGY_STYLE_DAILY_LOGIC_V1",
        "source_as_of_date": AS_OF,
        "source_common_panel_path": COMMON_PANEL.as_posix(),
        "source_common_panel_sha256": source_files["common_panel"]["sha256"],
        "source_category_states_path": CATEGORY_STATES.as_posix(),
        "source_category_states_sha256": source_files["category_states"]["sha256"],
        "source_state_machine_contract_sha256": validated[
            "state_machine_contract"
        ]["sha256"],
        "date_count": DATE_COUNT,
        "date_axis": "common_panel.dates",
        "profile_order": list(PROFILE_ORDER),
        "style_order": list(STYLE_ORDER),
        "logical_state_values": list(LOGICAL_STATES),
        "daily_result_values": list(DAILY_RESULTS),
        "profiles": output_profiles,
    }


def build_artifact_bytes(root: Path, as_of: str) -> dict[str, bytes]:
    validated = load_and_validate_inputs(root, as_of)
    daily_logic = build_daily_logic(validated)
    logic_content = json_bytes(daily_logic)
    manifest = {
        "schema_version": "1.0",
        "artifact_set_id": "STRATEGY_STYLE_DAILY_LOGIC_ARTIFACT_V1",
        "source_as_of_date": as_of,
        "source_files": validated["source_files"],
        "source_contracts": {
            "STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1": validated[
                "state_machine_contract"
            ]
        },
        "outputs": {
            "daily_logic": {
                "path": f"{OUTPUT_DIR.as_posix()}/daily_logic.json",
                "sha256": sha256_bytes(logic_content),
                "bytes": len(logic_content),
            }
        },
        "invariants": {
            "date_count": DATE_COUNT,
            "profile_count": len(PROFILE_ORDER),
            "style_count": len(STYLE_ORDER),
            "offline_only": True,
            "no_forward_information": True,
            "event_free": True,
        },
        "statuses": {
            "common_panel_status": "BUILT",
            "category_calculation_status": "IMPLEMENTED",
            "parameter_selection_status": "NOT_RUN",
            "entry_exit_state_machine_status": "IMPLEMENTED",
            "event_status": "NOT_BUILT",
            "walk_forward_status": "NOT_RUN",
            "allocation_status": "NOT_DEFINED",
            "backtest_status": "NOT_RUN",
            "integration_status": "DO_NOT_INTEGRATE",
        },
    }
    artifacts = {
        "manifest.json": json_bytes(manifest),
        "daily_logic.json": logic_content,
    }
    validate_artifact_bytes(artifacts)
    return artifacts


def validate_artifact_bytes(artifacts: dict[str, bytes]) -> None:
    _require(set(artifacts) == {"manifest.json", "daily_logic.json"}, "artifact inventory mismatch")
    manifest = json.loads(artifacts["manifest.json"])
    logic = json.loads(artifacts["daily_logic.json"])
    _require(logic.get("date_count") == DATE_COUNT, "daily logic date count mismatch")
    _require(logic.get("date_axis") == "common_panel.dates", "daily logic date axis mismatch")
    _require(logic.get("profile_order") == list(PROFILE_ORDER), "daily logic profile order mismatch")
    _require(logic.get("style_order") == list(STYLE_ORDER), "daily logic style order mismatch")
    _require([row.get("profile_id") for row in logic.get("profiles", [])] == list(PROFILE_ORDER), "daily logic profiles mismatch")
    allowed_transitions = {
        ("INACTIVE", "BLOCKED", "INACTIVE"),
        ("INACTIVE", "NO_CHANGE", "INACTIVE"),
        ("INACTIVE", "ENTRY_CANDIDATE", "ACTIVE"),
        ("ACTIVE", "BLOCKED", "ACTIVE"),
        ("ACTIVE", "HOLD_CANDIDATE", "ACTIVE"),
        ("ACTIVE", "EXIT_CANDIDATE", "INACTIVE"),
    }
    for profile in logic["profiles"]:
        styles = profile["style_logic"]
        _require([row.get("style_unit") for row in styles] == list(STYLE_ORDER), "output style order mismatch")
        _require(len(profile["concurrent_entry_candidate_set"]) == DATE_COUNT, "concurrent set length mismatch")
        for index, candidates in enumerate(profile["concurrent_entry_candidate_set"]):
            expected = [style["style_unit"] for style in styles if style["daily_result"][index] == "ENTRY_CANDIDATE"]
            _require(candidates == expected, "concurrent entry candidate set mismatch")
        for style in styles:
            before = style["state_before"]
            results = style["daily_result"]
            after = style["state_after"]
            _require(len(before) == len(results) == len(after) == DATE_COUNT, "style logic array length mismatch")
            _require(before[0] == "INACTIVE", "initial logical state mismatch")
            _require(set(before) <= set(LOGICAL_STATES) and set(after) <= set(LOGICAL_STATES), "invalid logical state")
            _require(set(results) <= set(DAILY_RESULTS), "invalid daily result")
            _require(all((a, b, c) in allowed_transitions for a, b, c in zip(before, results, after, strict=True)), "invalid state transition")
            _require(all(before[index] == after[index - 1] for index in range(1, DATE_COUNT)), "state recurrence mismatch")
    output = manifest["outputs"]["daily_logic"]
    _require(output["sha256"] == sha256_bytes(artifacts["daily_logic.json"]), "manifest output hash mismatch")
    _require(output["bytes"] == len(artifacts["daily_logic.json"]), "manifest output byte count mismatch")
    forbidden = (
        "event_id", "event_start", "event_end", "event_duration", "trigger_date",
        "execution_date", "forward_return", "outcome", "best_profile",
        "selected_profile", "target_weight", "position", "transaction_cost",
        "Sharpe", "Calmar", "maximum_drawdown",
    )
    combined = b"\n".join(artifacts.values()).decode("utf-8")
    _require(not any(term in combined for term in forbidden), "artifact contains forbidden downstream field")


def publish_artifacts(root: Path, artifacts: dict[str, bytes]) -> None:
    target = root / OUTPUT_DIR
    target.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".strategy-style-daily-", dir=target.parent))
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


def build_strategy_style_daily_logic(root: Path, as_of: str, *, publish: bool = True) -> dict[str, bytes]:
    artifacts = build_artifact_bytes(root, as_of)
    if publish:
        publish_artifacts(root, artifacts)
    return artifacts


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply the frozen strategy-style daily logic state machine.")
    parser.add_argument("--as-of", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        artifacts = build_strategy_style_daily_logic(ROOT, args.as_of)
    except (OSError, StrategyStyleDailyLogicError) as exc:
        print(f"strategy-style daily-logic build failed: {exc}")
        return 1
    manifest = json.loads(artifacts["manifest.json"])
    print(f"{OUTPUT_DIR.as_posix()}: {manifest['statuses']['entry_exit_state_machine_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
