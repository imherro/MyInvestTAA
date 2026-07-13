from __future__ import annotations


def build_constraint_diagnostics(monthly_allocations: list[dict], assets, config) -> dict:
    asset_by_id = {asset.asset_id: asset for asset in assets}
    violations: list[dict] = []
    cash_weights: list[float] = []
    cap_hits = {"single_asset_cap": 0, "theme_sleeve_cap": 0, "single_theme_cap": 0}

    for allocation in monthly_allocations:
        date = allocation.get("date")
        weights = allocation.get("weights", {})
        cash_weights.append(float(weights.get("CASH", 0.0)))
        theme_total = 0.0
        for asset_id, weight in weights.items():
            if asset_id == "CASH":
                continue
            value = float(weight)
            asset = asset_by_id.get(asset_id)
            if value > config.single_asset_max + 1e-8:
                violations.append({"date": date, "asset_id": asset_id, "constraint": "single_asset_max", "weight": value})
            if abs(value - config.single_asset_max) <= 1e-8:
                cap_hits["single_asset_cap"] += 1
            if asset and _is_theme(asset):
                theme_total += value
                if value > config.single_theme_max + 1e-8:
                    violations.append({"date": date, "asset_id": asset_id, "constraint": "single_theme_max", "weight": value})
                if abs(value - config.single_theme_max) <= 1e-8:
                    cap_hits["single_theme_cap"] += 1
        if theme_total > config.theme_sleeve_max + 1e-8:
            violations.append({"date": date, "constraint": "theme_sleeve_max", "weight": round(theme_total, 10)})
        if abs(theme_total - config.theme_sleeve_max) <= 1e-8:
            cap_hits["theme_sleeve_cap"] += 1

    count = len(cash_weights)
    cash_drag = {
        "average_cash": round(sum(cash_weights) / count, 6) if count else 0.0,
        "max_cash": round(max(cash_weights), 6) if cash_weights else 0.0,
        "months_cash_above_30": sum(weight > 0.30 for weight in cash_weights),
    }
    return {"violations": violations, "cash_drag": cash_drag, "cap_hits": cap_hits}


def _is_theme(asset) -> bool:
    return asset.sleeve == "theme" or asset.category == "theme"
