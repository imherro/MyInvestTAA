from __future__ import annotations

from engine.asset_repository import load_price_history
from engine.anchor import calculate_anchor_score
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
    recovery_score = _recovery_score(recovery)
    anchor_score = calculate_anchor_score(asset)
    opportunity_score = round(
        0.4 * drawdown_pressure + 0.3 * recovery_score + 0.3 * anchor_score,
        2,
    )

    return {
        "id": asset["id"],
        "name": asset["name"],
        "category": asset["category"],
        "drawdown_pressure": drawdown_pressure,
        "pressure_zone": pressure["zone"],
        "event_count": recovery.event_count,
        "recovered_events": recovery.recovered_events,
        "sample_confidence": recovery.sample_confidence,
        "recovery_probability": round(recovery.recovery_probability * 100, 2),
        "recovery_score": recovery_score,
        "anchor_score": anchor_score,
        "median_recovery_days": recovery.median_recovery_days,
        "median_forward_return_1y_pct": recovery.median_forward_return_1y_pct,
        "median_forward_return_2y_pct": recovery.median_forward_return_2y_pct,
        "median_forward_return_3y_pct": recovery.median_forward_return_3y_pct,
        "opportunity_score": opportunity_score,
    }


def _recovery_score(recovery) -> float:
    probability_score = recovery.recovery_probability * 100
    return_score = _return_score(recovery.median_forward_return_3y_pct)
    speed_score = _speed_score(recovery.median_recovery_days)
    return round(0.4 * probability_score + 0.3 * return_score + 0.3 * speed_score, 2)


def _return_score(forward_return_3y_pct: float | None) -> float:
    if forward_return_3y_pct is None:
        return 0.0
    return max(0.0, min(100.0, 50.0 + forward_return_3y_pct))


def _speed_score(median_recovery_days: float | int | None) -> float:
    if median_recovery_days is None:
        return 0.0
    if median_recovery_days <= 365:
        return 100.0
    if median_recovery_days <= 730:
        return 70.0
    if median_recovery_days <= 1095:
        return 50.0
    return 30.0
