from __future__ import annotations

from engine.drawdown.events import DrawdownEvent


def calculate_drawdown_percentile(events: list[DrawdownEvent], current_dd: float) -> dict:
    severities = sorted(abs(min(event.drawdown_pct, 0)) for event in events)
    current_severity = abs(min(current_dd, 0))

    if not severities or current_severity == 0:
        percentile = 0.0
    else:
        count = sum(1 for severity in severities if severity <= current_severity)
        percentile = count / len(severities)

    percentile = round(percentile, 4)
    return {
        "percentile": percentile,
        "zone": pressure_zone(percentile),
        "event_count": len(events),
        "current_drawdown_pct": round(current_dd, 4),
    }


def pressure_zone(percentile: float) -> str:
    if percentile >= 0.9:
        return "extreme"
    if percentile >= 0.75:
        return "high"
    if percentile >= 0.5:
        return "medium"
    return "normal"

