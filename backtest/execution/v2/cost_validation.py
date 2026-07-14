from __future__ import annotations

import json
import shutil
from uuid import uuid4

from backtest.execution.v2.cost_domain import (
    COST_TOLERANCE,
    SERIALIZATION_DECIMALS,
    VALUE_TOLERANCE,
    WEIGHT_TOLERANCE,
)
from backtest.execution.v2.costs import POLICY_PATH, load_cost_policy
from backtest.execution.v2.report import (
    COMMITTED as B1_COMMITTED,
    _hash_json,
    _promote,
    _read_json,
    _semantic_sha,
    _sha,
    verify_execution_v2_output_set,
)
from backtest.execution.v2.scenario import (
    ENGINE_SOURCE_PATHS,
    SOURCE_MANIFEST_PATHS,
    STRATEGY,
    build_expected_cost_run_identity,
)
from engine.asset_registry.loader import ROOT


REPORT = ROOT / "reports" / "execution_backtest_v2_b2_cost_report.json"
LEDGER = ROOT / "reports" / "execution_v2_b2_cost_ledger.json"
COMPARISON = ROOT / "reports" / "execution_v2_b1_b2_cost_comparison.json"
MANIFEST = ROOT / "reports" / "execution_v2_b2_cost_output_manifest.json"
COMMITTED = ROOT / "reports" / "execution_v2_b2_cost_COMMITTED.json"
ARTIFACTS = (REPORT, LEDGER, COMPARISON)


def write_cost_outputs(report, ledger, comparison):
    staging = ROOT / "reports" / ".execution-v2-b2-cost-staging" / uuid4().hex
    staging.mkdir(parents=True)
    try:
        values = {REPORT.name: report, LEDGER.name: ledger, COMPARISON.name: comparison}
        for name, value in values.items():
            (staging / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staged = {name: _read_json(staging / name) for name in values}
        cross_validate_cost_outputs(staged)
        artifacts = {
            name: {"sha256": _sha(staging / name), "semantic_sha256": _semantic_sha(staging / name)}
            for name in values
        }
        manifest = {
            "schema_version": "1.0",
            "run_id": report["run_id"],
            "scenario_id": report["scenario_id"],
            "policy_sha256": report["policy_sha256"],
            "b1_output_set_hash": report["b1_output_set_hash"],
            "date_grid_hash": comparison["date_grid_hash"],
            "input_source_manifest_hash": report["input_source_manifest_hash"],
            "artifacts": artifacts,
            "output_set_hash": _hash_json(artifacts),
            "verified": True,
            "errors": [],
        }
        manifest_path = staging / MANIFEST.name
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        marker = {
            "schema_version": "1.0",
            "run_id": report["run_id"],
            "output_set_hash": manifest["output_set_hash"],
            "manifest_sha256": _sha(manifest_path),
            "committed": True,
        }
        (staging / COMMITTED.name).write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _promote(staging, (*ARTIFACTS, MANIFEST, COMMITTED))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def load_cost_report():
    result = verify_cost_output_set()
    if not result["verified"]:
        return {
            "available": False,
            "status": "unavailable",
            "message": "execution V2 B2 cost output integrity failed",
            "errors": result["errors"],
        }
    return result["report"]


def verify_cost_output_set():
    errors = []
    values = {}
    try:
        b1_result = verify_execution_v2_output_set()
        if not b1_result["verified"]:
            errors.extend(f"B1 dependency invalid: {error}" for error in b1_result["errors"])
            return {"verified": False, "errors": errors, "report": {}}
        b1_report = b1_result["report"]
        b1_marker = _read_json(B1_COMMITTED)
        marker = _read_json(COMMITTED)
        manifest = _read_json(MANIFEST)

        if marker.get("committed") is not True:
            errors.append("cost committed marker is invalid")
        if marker.get("manifest_sha256") != _sha(MANIFEST):
            errors.append("cost manifest hash is invalid")
        if marker.get("output_set_hash") != manifest.get("output_set_hash"):
            errors.append("cost marker and manifest output-set hashes disagree")
        if marker.get("run_id") != manifest.get("run_id"):
            errors.append("cost marker and manifest run IDs disagree")
        if set(manifest.get("artifacts", {})) != {path.name for path in ARTIFACTS}:
            errors.append("cost manifest artifact set is invalid")

        for path in ARTIFACTS:
            expected = manifest.get("artifacts", {}).get(path.name, {})
            if expected.get("sha256") != _sha(path):
                errors.append(f"cost artifact raw hash mismatch: {path.name}")
            if expected.get("semantic_sha256") != _semantic_sha(path):
                errors.append(f"cost artifact semantic hash mismatch: {path.name}")
            values[path.name] = _read_json(path)
        if manifest.get("output_set_hash") != _hash_json(manifest.get("artifacts", {})):
            errors.append("cost manifest output-set hash cannot be reproduced")

        cross_validate_cost_outputs(values)
        report = values[REPORT.name]
        master_dates = [row["date"] for row in b1_report["daily_portfolio_states"]]
        identity = build_expected_cost_run_identity(
            verified_b1=b1_report,
            b1_marker=b1_marker,
            cost_policy_path=POLICY_PATH,
            master_dates=master_dates,
            strategy=STRATEGY,
            source_paths=ENGINE_SOURCE_PATHS,
        )
        current_policy_hash = identity["components"]["cost_policy_hash"]
        current_policy = load_cost_policy(POLICY_PATH)
        current_b1_hash = b1_marker["output_set_hash"]
        current_date_hash = identity["components"]["master_date_grid_hash"]

        if report.get("run_identity_components") != identity["components"]:
            errors.append("cost run identity components do not match current sources")
        if report.get("run_id") != identity["run_id"]:
            errors.append("cost run ID does not match current sources")
        if report.get("b1_baseline_run_id") != b1_report.get("run_id"):
            errors.append("cost B1 baseline run ID is invalid")
        if report.get("policy_sha256") != current_policy_hash:
            errors.append("cost report policy hash is stale")
        if report.get("policy") != current_policy.as_dict():
            errors.append("cost report policy payload is stale")
        if report.get("b1_output_set_hash") != current_b1_hash:
            errors.append("cost report B1 output-set hash is stale")
        if report.get("scenario_id") != identity["components"]["scenario_id"]:
            errors.append("cost report scenario ID is stale")

        source_manifest = report.get("source_manifest", {})
        if set(source_manifest) != set(SOURCE_MANIFEST_PATHS):
            errors.append("cost source-manifest path set is invalid")
        if report.get("input_source_manifest_hash") != _hash_json(source_manifest):
            errors.append("cost input source-manifest hash is invalid")
        for relative, details in source_manifest.items():
            if not (ROOT / relative).exists() or _sha(ROOT / relative) != details.get("sha256"):
                errors.append(f"cost source hash mismatch: {relative}")

        expected_manifest = {
            "run_id": identity["run_id"],
            "policy_sha256": current_policy_hash,
            "b1_output_set_hash": current_b1_hash,
            "date_grid_hash": current_date_hash,
            "input_source_manifest_hash": report.get("input_source_manifest_hash"),
            "scenario_id": identity["components"]["scenario_id"],
        }
        for field, expected in expected_manifest.items():
            if manifest.get(field) != expected:
                errors.append(f"cost manifest {field} is invalid")
        if manifest.get("verified") is not True or manifest.get("errors") != []:
            errors.append("cost manifest verification status is invalid")
        if report.get("production_actionable") is not False or report.get("eligible_to_replace_v1") is not False:
            errors.append("cost scenario production boundary is invalid")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {"verified": not errors, "errors": errors, "report": values.get(REPORT.name, {})}


def cross_validate_cost_outputs(values):
    report = values[REPORT.name]
    ledger = values[LEDGER.name]
    comparison = values[COMPARISON.name]
    shared_fields = (
        "run_id", "scenario_id", "policy_sha256", "b1_output_set_hash",
        "input_source_manifest_hash",
    )
    for field in shared_fields:
        if len({report.get(field), ledger.get(field), comparison.get(field)}) != 1:
            raise ValueError(f"cost artifacts disagree on {field}")

    rows = ledger.get("rows", [])
    expected_attribution = _recompute_cost_attribution(rows)
    if ledger.get("summary") != expected_attribution or report.get("cost_attribution") != expected_attribution:
        raise ValueError("cost attribution cannot be reproduced from ledger")

    dates = [row["date"] for row in report.get("net_cost_curve", [])]
    gross_dates = [row["date"] for row in report.get("gross_zero_cost_curve", [])]
    daily_rows = report.get("daily_portfolio_states", [])
    if dates != gross_dates or dates != [row["date"] for row in daily_rows]:
        raise ValueError("cost scenario date grids disagree")
    if _hash_json(dates) != comparison.get("date_grid_hash") or comparison.get("date_grid_equal") is not True:
        raise ValueError("cost comparison date-grid identity is invalid")

    rows_by_date = {}
    for index, row in enumerate(rows, start=1):
        if row.get("sequence_number") != index:
            raise ValueError("cost ledger sequence is not contiguous")
        if row.get("policy_sha256") != report.get("policy_sha256"):
            raise ValueError("cost ledger policy hash disagrees")
        if row.get("policy_id") != report.get("policy", {}).get("policy_id"):
            raise ValueError("cost ledger policy ID disagrees")
        expected_cash = row["pre_trade_cash"]
        if row["direction"] == "sell":
            expected_cash += row["gross_traded_notional"] - row["total_cost"]
        elif row["direction"] == "buy":
            expected_cash -= row["gross_traded_notional"] + row["total_cost"]
        else:
            raise ValueError("cost ledger direction is invalid")
        if abs(row["post_trade_cash"] - expected_cash) > VALUE_TOLERANCE:
            raise ValueError("cost ledger cash bridge is invalid")
        rows_by_date.setdefault(row["execution_date"], []).append(row)

    cumulative = 0.0
    expected_cumulative = []
    for daily in daily_rows:
        day_rows = rows_by_date.get(daily["date"], [])
        day_notional = round(sum(row["gross_traded_notional"] for row in day_rows), SERIALIZATION_DECIMALS)
        day_cost = round(sum(row["total_cost"] for row in day_rows), SERIALIZATION_DECIMALS)
        if abs(daily["gross_traded_notional"] - day_notional) > VALUE_TOLERANCE:
            raise ValueError("daily traded notional cannot be reproduced")
        if abs(daily["transaction_cost"] - day_cost) > COST_TOLERANCE:
            raise ValueError("daily transaction cost cannot be reproduced")
        if abs(daily["closing_nav"] - (daily["pre_trade_nav"] - day_cost)) > VALUE_TOLERANCE:
            raise ValueError("daily cost accounting bridge is invalid")
        if abs(sum(daily["weights"].values()) - 1.0) > WEIGHT_TOLERANCE:
            raise ValueError("daily weights do not reconcile")
        if day_rows:
            for previous, current in zip(day_rows, day_rows[1:]):
                if abs(previous["post_trade_cash"] - current["pre_trade_cash"]) > VALUE_TOLERANCE:
                    raise ValueError("cost ledger cash sequence is broken")
            if abs(day_rows[-1]["post_trade_cash"] - daily["closing_cash"]) > VALUE_TOLERANCE:
                raise ValueError("last ledger cash does not equal daily closing cash")
            event_rows = {}
            for row in day_rows:
                event_rows.setdefault(row["parent_event_id"], []).append(row)
            for event_group in event_rows.values():
                event_cost = sum(row["total_cost"] for row in event_group)
                if abs(event_group[0]["event_post_trade_nav"] - (event_group[0]["event_pre_trade_nav"] - event_cost)) > VALUE_TOLERANCE:
                    raise ValueError("event cost accounting bridge is invalid")
        cumulative += day_cost
        expected_cumulative.append({"date": daily["date"], "value": round(cumulative, SERIALIZATION_DECIMALS)})

    if report.get("cumulative_cost_curve") != expected_cumulative:
        raise ValueError("cumulative cost curve cannot be reproduced")
    total_cost = round(sum(row["total_cost"] for row in rows), SERIALIZATION_DECIMALS)
    if abs(report["reconciliation"]["ledger_total_cost"] - total_cost) > COST_TOLERANCE:
        raise ValueError("ledger total cost reconciliation is invalid")
    if abs(report["reconciliation"]["daily_total_cost"] - total_cost) > COST_TOLERANCE:
        raise ValueError("daily total cost reconciliation is invalid")
    ending_drag = round(
        report["gross_zero_cost_curve"][-1]["value"] - report["net_cost_curve"][-1]["value"],
        SERIALIZATION_DECIMALS,
    )
    if report["reconciliation"]["ending_nav_drag"] != ending_drag or comparison.get("ending_nav_drag") != ending_drag:
        raise ValueError("ending NAV drag cannot be reproduced")
    if comparison.get("cumulative_absolute_cost") != total_cost:
        raise ValueError("comparison cumulative cost is invalid")
    expected_comparison = {
        "b1_ending_nav": report["gross_zero_cost_curve"][-1]["value"],
        "b2_ending_nav": report["net_cost_curve"][-1]["value"],
        "annual_return_difference_percentage_points": round(
            (report["metrics_net_cost"]["annual_return"] - report["metrics_gross_zero_cost"]["annual_return"]) * 100,
            6,
        ),
        "elapsed_calendar_annual_return_difference_percentage_points": round(
            (
                report["metrics_net_cost"]["dated"]["elapsed_calendar_time_annualized"]
                - report["metrics_gross_zero_cost"]["dated"]["elapsed_calendar_time_annualized"]
            ) * 100,
            6,
        ),
        "max_drawdown_difference_percentage_points": round(
            (report["metrics_net_cost"]["max_drawdown"] - report["metrics_gross_zero_cost"]["max_drawdown"]) * 100,
            6,
        ),
        "sharpe_difference": round(
            report["metrics_net_cost"]["sharpe"] - report["metrics_gross_zero_cost"]["sharpe"],
            6,
        ),
        "turnover_notional_initial_nav_units": expected_attribution["total_notional"],
        "cost_per_unit_turnover": round(total_cost / expected_attribution["total_notional"], 10)
        if expected_attribution["total_notional"] else 0.0,
    }
    for field, expected in expected_comparison.items():
        if comparison.get(field) != expected:
            raise ValueError(f"comparison {field} cannot be reproduced")


def _recompute_cost_attribution(rows):
    def total(field):
        return round(sum(row[field] for row in rows), SERIALIZATION_DECIMALS)

    by_instrument = {}
    by_year = {}
    by_quality = {}
    for row in rows:
        cost = row["total_cost"]
        instrument = row["instrument_id"]
        year = row["execution_date"][:4]
        quality = row["mapping_quality"]
        by_instrument[instrument] = by_instrument.get(instrument, 0.0) + cost
        by_year[year] = by_year.get(year, 0.0) + cost
        by_quality[quality] = by_quality.get(quality, 0.0) + cost
    return {
        "buy_notional": round(
            sum(row["gross_traded_notional"] for row in rows if row["direction"] == "buy"),
            SERIALIZATION_DECIMALS,
        ),
        "sell_notional": round(
            sum(row["gross_traded_notional"] for row in rows if row["direction"] == "sell"),
            SERIALIZATION_DECIMALS,
        ),
        "total_notional": total("gross_traded_notional"),
        "commission_total": total("commission_cost"),
        "slippage_total": total("slippage_cost"),
        "tax_total": total("tax_cost"),
        "total_cost": total("total_cost"),
        "signal_rebalance_cost": round(
            sum(row["total_cost"] for row in rows if row["pending_adjustment_id"] is None),
            SERIALIZATION_DECIMALS,
        ),
        "completed_pending_cost": round(
            sum(row["total_cost"] for row in rows if row["pending_adjustment_id"] is not None),
            SERIALIZATION_DECIMALS,
        ),
        "cost_by_instrument": {
            key: round(value, SERIALIZATION_DECIMALS) for key, value in sorted(by_instrument.items())
        },
        "cost_by_year": {
            key: round(value, SERIALIZATION_DECIMALS) for key, value in sorted(by_year.items())
        },
        "cost_by_mapping_quality": {
            key: round(value, SERIALIZATION_DECIMALS) for key, value in sorted(by_quality.items())
        },
    }
