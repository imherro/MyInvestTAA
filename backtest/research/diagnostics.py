from __future__ import annotations

from backtest.research.attribution import build_factor_summary, build_selection_frequency
from backtest.research.constraints import build_constraint_diagnostics


def build_research_backtest_diagnostics(report: dict, aligned: dict, assets, config) -> dict:
    dates = aligned.get("dates", [])
    raw_start = _raw_start(assets)
    allocations = report.get("monthly_allocations", [])
    constraints = build_constraint_diagnostics(allocations, assets, config)
    return {
        "sample_period": {
            "raw_start": raw_start,
            "aligned_start": dates[0] if dates else None,
            "backtest_start": report.get("period", {}).get("start"),
            "reason": f"common-date alignment + {config.lookback_12m}-day lookback",
        },
        "constraint_impact": {
            "average_cash_weight": constraints["cash_drag"]["average_cash"],
            "max_cash_weight": constraints["cash_drag"]["max_cash"],
            "theme_cap_hit_months": constraints["cap_hits"]["theme_sleeve_cap"],
            "single_asset_cap_hit_months": constraints["cap_hits"]["single_asset_cap"],
        },
        "factor_summary": build_factor_summary(allocations),
        "selection_frequency": build_selection_frequency(allocations, assets),
        "warnings": _warnings(report, constraints),
    }


def _raw_start(assets) -> str | None:
    dates = [asset.data_start_date for asset in assets if asset.data_start_date]
    return min(dates) if dates else None


def _warnings(report: dict, constraints: dict) -> list[str]:
    warnings = ["Research Backtest period starts after common-date alignment and 12M lookback."]
    if constraints["cash_drag"]["max_cash"] > 0:
        warnings.append("Cash allocation can result from theme and single-asset constraints.")
    if report.get("period", {}).get("start") is None:
        warnings.append("No backtest sample period is available.")
    return warnings
