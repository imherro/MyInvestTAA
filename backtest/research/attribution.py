from __future__ import annotations


def build_factor_summary(monthly_allocations: list[dict]) -> dict:
    score_rows = [score for allocation in monthly_allocations for score in allocation.get("scores", {}).values()]
    if not score_rows:
        return {
            "average_momentum_6m": None,
            "average_momentum_12m": None,
            "average_drawdown_resilience": None,
            "score_observations": 0,
        }
    return {
        "average_momentum_6m": _average(score_rows, "momentum_6m"),
        "average_momentum_12m": _average(score_rows, "momentum_12m"),
        "average_drawdown_resilience": _average(score_rows, "drawdown_resilience"),
        "score_observations": len(score_rows),
    }


def build_selection_frequency(monthly_allocations: list[dict], assets) -> list[dict]:
    names = {asset.asset_id: asset.name for asset in assets}
    counts: dict[str, int] = {}
    for allocation in monthly_allocations:
        for asset_id in allocation.get("scores", {}):
            counts[asset_id] = counts.get(asset_id, 0) + 1
    return [
        {"asset_id": asset_id, "name": names.get(asset_id, asset_id), "selected_months": count}
        for asset_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _average(rows: list[dict], field: str) -> float:
    return round(sum(float(row.get(field, 0.0)) for row in rows) / len(rows), 6)
