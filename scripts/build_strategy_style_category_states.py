"""Build deterministic strategy-style common-panel and category-state artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-07-15"
OUTPUT_RELATIVE = Path("data/strategy_style_category_calculations_v1")
UNIVERSE_RELATIVE = Path("config/strategy_style_research_universe_v1.json")
DATASET_MANIFEST_RELATIVE = Path("data/strategy_style_research/manifest.json")
CALENDAR_RELATIVE = Path("data/strategy_style_research/sse_trade_calendar.json")
QUALIFICATION_RELATIVE = Path(
    "reports/strategy_research/strategy_style_data_qualification_v1.json"
)
CONTRACT_RELATIVES = (
    Path("docs/STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1.md"),
    Path("docs/STRATEGY_STYLE_OBSERVATION_DATA_CONTRACT_V1.md"),
    Path("docs/STRATEGY_STYLE_SIGNAL_CATEGORY_PREREGISTRATION_V1.md"),
    Path("docs/STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md"),
    Path("docs/STRATEGY_STYLE_CATEGORY_CALCULATION_PREREGISTRATION_V1.md"),
)
MEMBER_SPECS = (
    ("CN2296.CNI", "growth", "创成长R"),
    ("CN2371.CNI", "value", "国证价值R"),
    ("H00015.CSI", "dividend", "红利收益"),
    ("H00922.CSI", "dividend", "中红收益"),
    ("480092.CNI", "cash_flow", "国证自由现金流指数R"),
)
STYLE_ORDER = ("growth", "value", "dividend", "cash_flow")
CATEGORIES = (
    "drawdown_pressure",
    "absolute_stabilization",
    "relative_stabilization",
    "adverse_continuation",
)
PROFILES = (
    ("PROFILE_A", 0.10, 10, 20, 10),
    ("PROFILE_B", 0.15, 20, 40, 20),
    ("PROFILE_C", 0.20, 40, 60, 40),
)
COMMON_START = "2013-01-04"
COMMON_SESSION_COUNT = 3284
COMMON_OBSERVATION_COUNT = 16420
COMMON_STATES = ("MET", "NOT_MET", "UNAVAILABLE")
AGREEMENT_STATES = ("AGREEMENT", "CONFLICT", "UNAVAILABLE")


class StrategyStyleCategoryStateError(RuntimeError):
    """Raised when formal inputs or generated artifacts violate the contract."""


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
    path = root / relative
    try:
        return path.read_bytes()
    except OSError as exc:
        raise StrategyStyleCategoryStateError(f"cannot read formal input: {relative}") from exc


def _read_json(root: Path, relative: Path) -> tuple[Any, bytes]:
    content = _read_bytes(root, relative)
    try:
        return json.loads(content.decode("utf-8")), content
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StrategyStyleCategoryStateError(f"invalid JSON input: {relative}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StrategyStyleCategoryStateError(message)


def load_and_validate_inputs(root: Path, as_of: str) -> dict[str, Any]:
    """Load only the frozen formal inputs and fail closed on any mismatch."""
    _require(as_of == AS_OF, f"--as-of must be {AS_OF}")
    universe, universe_bytes = _read_json(root, UNIVERSE_RELATIVE)
    manifest, manifest_bytes = _read_json(root, DATASET_MANIFEST_RELATIVE)
    calendar, calendar_bytes = _read_json(root, CALENDAR_RELATIVE)
    qualification, qualification_bytes = _read_json(root, QUALIFICATION_RELATIVE)

    _require(isinstance(universe, dict), "universe must be an object")
    _require(isinstance(manifest, dict), "source manifest must be an object")
    _require(isinstance(calendar, dict), "calendar must be an object")
    _require(isinstance(qualification, dict), "qualification must be an object")
    _require(manifest.get("dataset_id") == "STRATEGY_STYLE_RESEARCH_DATASET_V1", "source dataset id mismatch")
    _require(manifest.get("as_of_date") == as_of, "source manifest as-of mismatch")
    _require(calendar.get("as_of_date") == as_of, "calendar as-of mismatch")
    _require(qualification.get("as_of_date") == as_of, "qualification as-of mismatch")
    _require(qualification.get("overall_status") == "QUALIFIED", "source qualification is not QUALIFIED")

    universe_hash = sha256_bytes(universe_bytes)
    manifest_hash = sha256_bytes(manifest_bytes)
    calendar_hash = sha256_bytes(calendar_bytes)
    _require(manifest.get("universe_config_sha256") == universe_hash, "manifest universe hash mismatch")
    _require(qualification.get("source_universe_config_sha256") == universe_hash, "qualification universe hash mismatch")
    _require(qualification.get("source_manifest_sha256") == manifest_hash, "qualification manifest hash mismatch")
    _require(manifest.get("calendar_sha256") == calendar_hash, "calendar hash mismatch")

    expected_ids = [item[0] for item in MEMBER_SPECS]
    expected_styles = [item[1] for item in MEMBER_SPECS]
    assets = universe.get("assets")
    _require(isinstance(assets, list), "universe assets must be an array")
    _require([row.get("asset_id") for row in assets] == expected_ids, "universe member order mismatch")
    _require([row.get("style_family") for row in assets] == expected_styles, "universe style map mismatch")
    _require([row.get("research_order") for row in assets] == list(range(1, 6)), "universe research order mismatch")
    for configured, expected in zip(assets, MEMBER_SPECS, strict=True):
        _require(configured.get("display_name") == expected[2], f"display name mismatch: {expected[0]}")
        _require(configured.get("return_basis") == "total_return", f"return basis mismatch: {expected[0]}")
        _require(configured.get("enabled") is True, f"disabled member: {expected[0]}")

    manifest_assets = manifest.get("assets")
    qualification_assets = qualification.get("assets")
    _require(isinstance(manifest_assets, list), "manifest assets must be an array")
    _require(isinstance(qualification_assets, list), "qualification assets must be an array")
    _require([row.get("asset_id") for row in manifest_assets] == expected_ids, "manifest member order mismatch")
    _require([row.get("asset_id") for row in qualification_assets] == expected_ids, "qualification member order mismatch")

    prices: dict[str, list[dict[str, Any]]] = {}
    price_sources: dict[str, dict[str, Any]] = {}
    for expected, manifest_asset, qualified_asset in zip(
        MEMBER_SPECS, manifest_assets, qualification_assets, strict=True
    ):
        asset_id, style, display_name = expected
        for row, label in ((manifest_asset, "manifest"), (qualified_asset, "qualification")):
            _require(row.get("style_family") == style, f"{label} style mismatch: {asset_id}")
            _require(row.get("display_name") == display_name, f"{label} name mismatch: {asset_id}")
            _require(row.get("research_order") == expected_ids.index(asset_id) + 1, f"{label} order mismatch: {asset_id}")
        _require(qualified_asset.get("qualified") is True, f"member is not qualified: {asset_id}")
        _require(qualified_asset.get("blockers") == [], f"member has qualification blockers: {asset_id}")
        price_relative = Path(str(manifest_asset.get("price_file", "")))
        _require(str(price_relative).replace("\\", "/") == str(qualified_asset.get("price_file", "")).replace("\\", "/"), f"price path mismatch: {asset_id}")
        price_data, price_content = _read_json(root, price_relative)
        price_hash = sha256_bytes(price_content)
        _require(price_hash == manifest_asset.get("price_file_sha256"), f"manifest price hash mismatch: {asset_id}")
        _require(price_hash == qualified_asset.get("price_file_sha256"), f"qualification price hash mismatch: {asset_id}")
        _require(isinstance(price_data, list) and price_data, f"invalid price rows: {asset_id}")
        dates = [row.get("date") for row in price_data]
        _require(all(isinstance(row, dict) for row in price_data), f"invalid price row: {asset_id}")
        _require(dates == sorted(set(dates)), f"price dates not sorted and unique: {asset_id}")
        _require(all(date <= as_of for date in dates), f"price contains data after as-of: {asset_id}")
        _require(all(row.get("return_basis") == "total_return" for row in price_data), f"non-total-return row: {asset_id}")
        _require(all(isinstance(row.get("close"), (int, float)) and math.isfinite(row["close"]) and row["close"] > 0 for row in price_data), f"invalid close: {asset_id}")
        prices[asset_id] = price_data
        price_sources[asset_id] = {
            "path": price_relative.as_posix(),
            "sha256": price_hash,
            "bytes": len(price_content),
        }

    calendar_dates = calendar.get("dates")
    _require(isinstance(calendar_dates, list), "calendar dates must be an array")
    _require(calendar_dates == sorted(set(calendar_dates)), "calendar dates not sorted and unique")
    _require(all(date <= as_of for date in calendar_dates), "calendar contains data after as-of")
    price_date_sets = {
        asset_id: {row["date"] for row in rows} for asset_id, rows in prices.items()
    }
    common_dates = [
        date
        for date in calendar_dates
        if date >= COMMON_START and all(date in dates for dates in price_date_sets.values())
    ]
    _require(len(common_dates) == COMMON_SESSION_COUNT, "common session count mismatch")
    _require(common_dates[0] == COMMON_START and common_dates[-1] == as_of, "common date bounds mismatch")
    for asset_id, dates in price_date_sets.items():
        _require(all(date in dates for date in common_dates), f"member incomplete on common dates: {asset_id}")

    source_files = {
        "universe_config": _source_record(UNIVERSE_RELATIVE, universe_bytes),
        "source_manifest": _source_record(DATASET_MANIFEST_RELATIVE, manifest_bytes),
        "calendar": _source_record(CALENDAR_RELATIVE, calendar_bytes),
        "qualification": _source_record(QUALIFICATION_RELATIVE, qualification_bytes),
        "prices": price_sources,
    }
    source_contracts = {
        path.stem: _source_record(path, _read_bytes(root, path))
        for path in CONTRACT_RELATIVES
    }
    return {
        "prices": prices,
        "common_dates": common_dates,
        "source_files": source_files,
        "source_contracts": source_contracts,
    }


def _source_record(relative: Path, content: bytes) -> dict[str, Any]:
    return {"path": relative.as_posix(), "sha256": sha256_bytes(content), "bytes": len(content)}


def build_common_panel(validated: dict[str, Any]) -> dict[str, Any]:
    dates = validated["common_dates"]
    members: list[dict[str, Any]] = []
    for asset_id, style, display_name in MEMBER_SPECS:
        by_date = {row["date"]: float(row["close"]) for row in validated["prices"][asset_id]}
        closes = [by_date[date] for date in dates]
        initial = closes[0]
        normalized = [value / initial for value in closes]
        daily_returns: list[float | None] = [None]
        daily_returns.extend(closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes)))
        running_peak: list[float] = []
        current_peak = 1.0
        for level in normalized:
            current_peak = max(current_peak, level)
            running_peak.append(current_peak)
        members.append(
            {
                "asset_id": asset_id,
                "style_unit": style,
                "display_name": display_name,
                "return_basis": "total_return",
                "close": closes,
                "daily_total_return": daily_returns,
                "normalized_level": normalized,
                "cumulative_total_return": [level - 1.0 for level in normalized],
                "running_peak_level": running_peak,
                "drawdown": [level / peak - 1.0 for level, peak in zip(normalized, running_peak, strict=True)],
            }
        )
    return {
        "schema_version": "1.0",
        "dataset_id": "STRATEGY_STYLE_COMMON_PANEL_V1",
        "source_dataset_id": "STRATEGY_STYLE_RESEARCH_DATASET_V1",
        "source_as_of_date": AS_OF,
        "common_observation_start": COMMON_START,
        "common_observation_end": AS_OF,
        "session_count": len(dates),
        "member_count": len(members),
        "style_unit_count": len(STYLE_ORDER),
        "member_date_observation_count": len(dates) * len(members),
        "dates": dates,
        "members": members,
    }


def _horizon_returns(levels: list[float], horizon: int) -> list[float | None]:
    return [None if index < horizon else level / levels[index - horizon] - 1.0 for index, level in enumerate(levels)]


def _prior_minima(levels: list[float], lookback: int) -> list[float | None]:
    return [None if index < lookback else min(levels[index - lookback : index]) for index in range(len(levels))]


def _median_four(values: list[float]) -> float:
    ordered = sorted(values)
    return (ordered[1] + ordered[2]) / 2.0


def _state(value: float | None, predicate: Any) -> str:
    if value is None or not math.isfinite(value):
        return "UNAVAILABLE"
    return "MET" if predicate(value) else "NOT_MET"


def _aggregate_dividend(member_states: list[dict[str, list[str]]]) -> tuple[dict[str, list[str]], list[str]]:
    aggregated = {category: [] for category in CATEGORIES}
    agreement: list[str] = []
    for index in range(len(next(iter(member_states[0].values())))):
        pairs = {category: [row[category][index] for row in member_states] for category in CATEGORIES}
        for category, values in pairs.items():
            if "UNAVAILABLE" in values:
                result = "UNAVAILABLE"
            elif category == "adverse_continuation":
                result = "MET" if "MET" in values else "NOT_MET"
            else:
                result = "MET" if values == ["MET", "MET"] else "NOT_MET"
            aggregated[category].append(result)
        if any("UNAVAILABLE" in values for values in pairs.values()):
            agreement.append("UNAVAILABLE")
        elif all(values[0] == values[1] for values in pairs.values()):
            agreement.append("AGREEMENT")
        else:
            agreement.append("CONFLICT")
    return aggregated, agreement


def build_category_states(common_panel: dict[str, Any], calculation_contract_sha256: str) -> dict[str, Any]:
    members = common_panel["members"]
    dates = common_panel["dates"]
    profiles: list[dict[str, Any]] = []
    for profile_id, threshold, absolute_horizon, relative_horizon, adverse_lookback in PROFILES:
        closes = {member["asset_id"]: member["close"] for member in members}
        levels = {member["asset_id"]: member["normalized_level"] for member in members}
        absolute = {asset_id: _horizon_returns(values, absolute_horizon) for asset_id, values in closes.items()}
        relative = {asset_id: _horizon_returns(values, relative_horizon) for asset_id, values in closes.items()}
        prior = {asset_id: _prior_minima(values, adverse_lookback) for asset_id, values in levels.items()}
        calculations: list[dict[str, Any]] = []
        member_state_map: dict[str, dict[str, list[str]]] = {}
        for member in members:
            asset_id = member["asset_id"]
            peer_medians: list[float | None] = []
            gaps: list[float | None] = []
            for index, own_return in enumerate(relative[asset_id]):
                peer_values = [values[index] for peer_id, values in relative.items() if peer_id != asset_id]
                if own_return is None or any(value is None for value in peer_values):
                    peer_medians.append(None)
                    gaps.append(None)
                else:
                    median = _median_four([float(value) for value in peer_values])
                    peer_medians.append(median)
                    gaps.append(own_return - median)
            states = {
                "drawdown_pressure": [_state(value, lambda item, t=threshold: item <= -t) for value in member["drawdown"]],
                "absolute_stabilization": [_state(value, lambda item: item >= 0.0) for value in absolute[asset_id]],
                "relative_stabilization": [_state(value, lambda item: item >= 0.0) for value in gaps],
                "adverse_continuation": [
                    "UNAVAILABLE" if minimum is None else ("MET" if level < minimum else "NOT_MET")
                    for level, minimum in zip(levels[asset_id], prior[asset_id], strict=True)
                ],
            }
            member_state_map[asset_id] = states
            calculations.append(
                {
                    "asset_id": asset_id,
                    "absolute_horizon_return": absolute[asset_id],
                    "relative_horizon_return": relative[asset_id],
                    "relative_peer_median_return": peer_medians,
                    "relative_return_gap": gaps,
                    "adverse_prior_min_level": prior[asset_id],
                    "states": states,
                }
            )
        style_states: list[dict[str, Any]] = []
        dividend_agreement: list[str] = []
        for style in STYLE_ORDER:
            style_ids = [asset_id for asset_id, member_style, _ in MEMBER_SPECS if member_style == style]
            if style == "dividend":
                states, dividend_agreement = _aggregate_dividend([member_state_map[asset_id] for asset_id in style_ids])
                style_record = {"style_unit": style, "member_asset_ids": style_ids, "states": states, "dividend_member_agreement": dividend_agreement}
            else:
                style_record = {"style_unit": style, "member_asset_ids": style_ids, "states": member_state_map[style_ids[0]]}
            style_states.append(style_record)
        availability = {
            "drawdown_pressure_first_available_date": _first_available(dates, [member_state_map[asset_id]["drawdown_pressure"] for asset_id in member_state_map]),
            "absolute_stabilization_first_available_date": _first_available(dates, [member_state_map[asset_id]["absolute_stabilization"] for asset_id in member_state_map]),
            "relative_stabilization_first_available_date": _first_available(dates, [member_state_map[asset_id]["relative_stabilization"] for asset_id in member_state_map]),
            "adverse_continuation_first_available_date": _first_available(dates, [member_state_map[asset_id]["adverse_continuation"] for asset_id in member_state_map]),
            "dividend_member_agreement_first_available_date": _first_available(dates, [dividend_agreement]),
            "all_categories_first_available_date": _first_available(
                dates,
                [member_state_map[asset_id][category] for asset_id in member_state_map for category in CATEGORIES] + [dividend_agreement],
            ),
        }
        profiles.append(
            {
                "profile_id": profile_id,
                "parameters": {
                    "pressure_threshold": threshold,
                    "absolute_horizon": absolute_horizon,
                    "relative_horizon": relative_horizon,
                    "adverse_lookback": adverse_lookback,
                },
                "availability": availability,
                "member_calculations": calculations,
                "style_states": style_states,
            }
        )
    return {
        "schema_version": "1.0",
        "dataset_id": "STRATEGY_STYLE_CATEGORY_STATES_V1",
        "source_common_panel_path": f"{OUTPUT_RELATIVE.as_posix()}/common_panel.json",
        "source_common_panel_sha256": sha256_bytes(json_bytes(common_panel)),
        "source_calculation_contract_sha256": calculation_contract_sha256,
        "date_count": len(dates),
        "date_axis": "common_panel.dates",
        "profile_order": [item[0] for item in PROFILES],
        "common_state_values": list(COMMON_STATES),
        "agreement_state_values": list(AGREEMENT_STATES),
        "profiles": profiles,
    }


def _first_available(dates: list[str], arrays: list[list[str]]) -> str | None:
    for index, current_date in enumerate(dates):
        if all(values[index] != "UNAVAILABLE" for values in arrays):
            return current_date
    return None


def build_artifact_bytes(root: Path, as_of: str) -> dict[str, bytes]:
    validated = load_and_validate_inputs(root, as_of)
    panel = build_common_panel(validated)
    calculation_hash = validated["source_contracts"]["STRATEGY_STYLE_CATEGORY_CALCULATION_PREREGISTRATION_V1"]["sha256"]
    states = build_category_states(panel, calculation_hash)
    panel_content = json_bytes(panel)
    states_content = json_bytes(states)
    manifest = {
        "schema_version": "1.0",
        "artifact_set_id": "STRATEGY_STYLE_CATEGORY_CALCULATIONS_V1",
        "source_as_of_date": as_of,
        "source_dataset_id": "STRATEGY_STYLE_RESEARCH_DATASET_V1",
        "source_files": validated["source_files"],
        "source_contracts": validated["source_contracts"],
        "outputs": {
            "common_panel": {"path": f"{OUTPUT_RELATIVE.as_posix()}/common_panel.json", "sha256": sha256_bytes(panel_content), "bytes": len(panel_content)},
            "category_states": {"path": f"{OUTPUT_RELATIVE.as_posix()}/category_states.json", "sha256": sha256_bytes(states_content), "bytes": len(states_content)},
        },
        "invariants": {
            "common_session_count": COMMON_SESSION_COUNT,
            "member_count": len(MEMBER_SPECS),
            "style_unit_count": len(STYLE_ORDER),
            "member_date_observation_count": COMMON_OBSERVATION_COUNT,
            "offline_only": True,
            "no_forward_information": True,
        },
        "profile_order": [item[0] for item in PROFILES],
        "statuses": {
            "common_panel_status": "BUILT",
            "category_calculation_implementation_status": "IMPLEMENTED",
            "parameter_selection_status": "NOT_RUN",
            "entry_exit_state_machine_status": "NOT_APPLIED",
            "event_status": "NOT_BUILT",
            "walk_forward_status": "NOT_RUN",
            "allocation_status": "NOT_DEFINED",
            "backtest_status": "NOT_RUN",
            "integration_status": "DO_NOT_INTEGRATE",
        },
    }
    artifacts = {
        "manifest.json": json_bytes(manifest),
        "common_panel.json": panel_content,
        "category_states.json": states_content,
    }
    validate_artifact_bytes(artifacts)
    return artifacts


def validate_artifact_bytes(artifacts: dict[str, bytes]) -> None:
    _require(set(artifacts) == {"manifest.json", "common_panel.json", "category_states.json"}, "artifact inventory mismatch")
    decoded = {name: json.loads(content.decode("utf-8")) for name, content in artifacts.items()}
    manifest = decoded["manifest.json"]
    panel = decoded["common_panel.json"]
    states = decoded["category_states.json"]
    _require(panel.get("session_count") == COMMON_SESSION_COUNT, "panel session count mismatch")
    _require(panel.get("member_date_observation_count") == COMMON_OBSERVATION_COUNT, "panel observation count mismatch")
    _require(states.get("date_count") == COMMON_SESSION_COUNT, "state date count mismatch")
    _require(states.get("date_axis") == "common_panel.dates", "state date axis mismatch")
    _require(states.get("source_common_panel_sha256") == sha256_bytes(artifacts["common_panel.json"]), "state panel hash mismatch")
    for key, filename in (("common_panel", "common_panel.json"), ("category_states", "category_states.json")):
        output = manifest["outputs"][key]
        _require(output["sha256"] == sha256_bytes(artifacts[filename]), f"manifest output hash mismatch: {filename}")
        _require(output["bytes"] == len(artifacts[filename]), f"manifest output byte count mismatch: {filename}")
    forbidden = (
        "ENTRY_CANDIDATE", "HOLD_CANDIDATE", "EXIT_CANDIDATE", "BUY", "SELL",
        "TARGET_WEIGHT", "event_id", "forward_return", "best_profile",
    )
    combined = b"\n".join(artifacts.values()).decode("utf-8")
    _require(not any(term in combined for term in forbidden), "artifact contains forbidden downstream field")


def publish_artifacts(root: Path, artifacts: dict[str, bytes]) -> None:
    """Atomically replace the complete artifact directory after staged validation."""
    target = root / OUTPUT_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".strategy-style-category-", dir=target.parent))
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


def build_strategy_style_category_states(root: Path, as_of: str, *, publish: bool = True) -> dict[str, bytes]:
    artifacts = build_artifact_bytes(root, as_of)
    if publish:
        publish_artifacts(root, artifacts)
    return artifacts


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic strategy-style category-state artifacts.")
    parser.add_argument("--as-of", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        artifacts = build_strategy_style_category_states(ROOT, args.as_of)
    except (OSError, StrategyStyleCategoryStateError) as exc:
        print(f"strategy-style category-state build failed: {exc}")
        return 1
    manifest = json.loads(artifacts["manifest.json"])
    print(f"{OUTPUT_RELATIVE.as_posix()}: {manifest['statuses']['category_calculation_implementation_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
