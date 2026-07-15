from __future__ import annotations

import json
from pathlib import Path

from backtest.research.engine import run_research_backtest
from backtest.research.metrics import build_metrics
from engine.asset_registry.loader import ROOT


RESEARCH_UNIVERSE_COMPARISON_REPORT = ROOT / "reports" / "research_universe_comparison_report.json"


def build_research_universe_comparison(assets, price_data, added_asset_id: str) -> dict:
    if not any(asset.asset_id == added_asset_id for asset in assets):
        raise ValueError(f"unknown added research asset: {added_asset_id}")

    baseline_assets = [asset for asset in assets if asset.asset_id != added_asset_id]
    baseline = run_research_backtest(baseline_assets, price_data)
    candidate = run_research_backtest(assets, price_data)
    if not baseline.get("available") or not candidate.get("available"):
        return {
            "available": False,
            "added_asset_id": added_asset_id,
            "baseline_errors": baseline.get("errors", []),
            "candidate_errors": candidate.get("errors", []),
        }

    baseline_curve, candidate_curve = _common_normalized_curves(
        baseline["equity_curve"], candidate["equity_curve"]
    )
    baseline_metrics = build_metrics(baseline_curve)
    candidate_metrics = build_metrics(candidate_curve)
    selection_impact = _selection_impact(
        baseline.get("monthly_allocations", []),
        candidate.get("monthly_allocations", []),
        added_asset_id,
    )
    return {
        "available": True,
        "schema_version": "1.0",
        "added_asset_id": added_asset_id,
        "baseline_universe_count": baseline["universe_count"],
        "candidate_universe_count": candidate["universe_count"],
        "comparison_period": {
            "start": candidate_curve[0]["date"],
            "end": candidate_curve[-1]["date"],
            "trading_days": len(candidate_curve),
        },
        "baseline": {"metrics": baseline_metrics, "equity_curve": baseline_curve},
        "candidate": {"metrics": candidate_metrics, "equity_curve": candidate_curve},
        "metric_deltas": {
            key: round(candidate_metrics[key] - baseline_metrics[key], 6)
            for key in baseline_metrics
        },
        "selection_impact": selection_impact,
        "warnings": [
            "The baseline and candidate use the same dates and the same scoring policy.",
            "This comparison changes only the allocation-eligible research universe.",
            "Research index performance is not ETF execution performance.",
        ],
    }


def write_research_universe_comparison(report: dict, path: Path | None = None) -> Path:
    target = path or RESEARCH_UNIVERSE_COMPARISON_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_research_universe_comparison(path: Path | None = None) -> dict:
    target = path or RESEARCH_UNIVERSE_COMPARISON_REPORT
    if not target.exists():
        return {"available": False, "message": "research universe comparison not generated yet"}
    return json.loads(target.read_text(encoding="utf-8"))


def _common_normalized_curves(baseline_rows: list[dict], candidate_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    baseline_by_date = {row["date"]: float(row["value"]) for row in baseline_rows}
    candidate_by_date = {row["date"]: float(row["value"]) for row in candidate_rows}
    dates = sorted(set(baseline_by_date) & set(candidate_by_date))
    if len(dates) < 2:
        raise ValueError("baseline and candidate do not have enough common dates")
    baseline_base = baseline_by_date[dates[0]]
    candidate_base = candidate_by_date[dates[0]]
    return (
        [{"date": date, "value": round(baseline_by_date[date] / baseline_base, 8)} for date in dates],
        [{"date": date, "value": round(candidate_by_date[date] / candidate_base, 8)} for date in dates],
    )


def _selection_impact(baseline_allocations: list[dict], candidate_allocations: list[dict], added_asset_id: str) -> dict:
    baseline_by_date = {row["date"]: row.get("weights", {}) for row in baseline_allocations}
    selected_rows = [
        row for row in candidate_allocations if float(row.get("weights", {}).get(added_asset_id, 0.0)) > 0
    ]
    weights = [float(row["weights"][added_asset_id]) for row in selected_rows]
    displacement: dict[str, float] = {}
    for row in selected_rows:
        baseline_weights = baseline_by_date.get(row["date"], {})
        candidate_weights = row.get("weights", {})
        for asset_id, baseline_weight in baseline_weights.items():
            if asset_id in {"CASH", added_asset_id}:
                continue
            decrease = float(baseline_weight) - float(candidate_weights.get(asset_id, 0.0))
            if decrease > 1e-10:
                displacement[asset_id] = displacement.get(asset_id, 0.0) + decrease
    return {
        "selected_months": len(selected_rows),
        "total_candidate_months": len(candidate_allocations),
        "selected_month_ratio": round(len(selected_rows) / len(candidate_allocations), 6)
        if candidate_allocations
        else 0.0,
        "average_weight_when_selected": round(sum(weights) / len(weights), 6) if weights else 0.0,
        "maximum_weight": round(max(weights), 6) if weights else 0.0,
        "top_displaced_assets": [
            {"asset_id": asset_id, "cumulative_weight_reduction": round(value, 6)}
            for asset_id, value in sorted(displacement.items(), key=lambda item: item[1], reverse=True)[:5]
        ],
    }
