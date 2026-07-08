from __future__ import annotations

from engine.asset_repository import load_price_history
from engine.drawdown import calculate_drawdown, calculate_drawdown_percentile, detect_drawdown_events
from engine.recovery import analyze_recovery_events


def build_opportunity_ranking(assets: list[dict]) -> list[dict]:
    ranking = [score_asset_opportunity(asset) for asset in assets]
    return sorted(ranking, key=lambda item: item["opportunity_score"], reverse=True)


def score_asset_opportunity(asset: dict) -> dict:
    history = load_price_history(asset["id"])
    events = detect_drawdown_events(history)
    current = calculate_drawdown([float(row["close"]) for row in history])
    pressure = calculate_drawdown_percentile(events, current.current_drawdown_pct)
    recovery = analyze_recovery_events(events, history, asset_id=asset["id"])

    drawdown_pressure = round(pressure["percentile"] * 100, 2)
    recovery_probability = round(recovery.recovery_probability * 100, 2)
    opportunity_score = round(0.5 * drawdown_pressure + 0.5 * recovery_probability, 2)

    return {
        "id": asset["id"],
        "name": asset["name"],
        "category": asset["category"],
        "drawdown_pressure": drawdown_pressure,
        "pressure_zone": pressure["zone"],
        "event_count": recovery.event_count,
        "recovered_events": recovery.recovered_events,
        "recovery_probability": recovery_probability,
        "median_recovery_days": recovery.median_recovery_days,
        "median_forward_return_1y_pct": recovery.median_forward_return_1y_pct,
        "median_forward_return_2y_pct": recovery.median_forward_return_2y_pct,
        "median_forward_return_3y_pct": recovery.median_forward_return_3y_pct,
        "opportunity_score": opportunity_score,
    }

