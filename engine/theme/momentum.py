from __future__ import annotations

from datetime import date, timedelta

from engine.theme.models import ThemeMomentumScore


MOMENTUM_WINDOWS = {
    "return_21d": (21, 0.20),
    "return_63d": (63, 0.30),
    "return_126d": (126, 0.30),
    "return_252d": (252, 0.20),
}


def calculate_theme_momentum(
    theme: str,
    member_histories: dict[str, list[dict]],
) -> ThemeMomentumScore:
    windows: dict[str, float | None] = {}
    weighted_return = 0.0
    active_weight = 0.0
    for label, (days, weight) in MOMENTUM_WINDOWS.items():
        returns = [
            item
            for item in (_lookback_return(history, days) for history in member_histories.values())
            if item is not None
        ]
        value = round(sum(returns) / len(returns), 6) if returns else None
        windows[label] = value
        if value is not None:
            weighted_return += value * weight
            active_weight += weight
    normalized_return = weighted_return / active_weight if active_weight else 0.0
    return ThemeMomentumScore(
        theme=theme,
        momentum_score=_score_from_return(normalized_return),
        weighted_return=round(normalized_return, 6),
        members=sorted(member_histories),
        windows=windows,
    )


def _lookback_return(history: list[dict], days: int) -> float | None:
    rows = sorted(history, key=lambda item: str(item["date"]))
    if len(rows) < 2:
        return None
    current = rows[-1]
    current_close = float(current["close"])
    if current_close <= 0:
        return None
    target_date = date.fromisoformat(str(current["date"])) - timedelta(days=days)
    previous_close = _close_on_or_before(rows, target_date)
    if previous_close is None or previous_close <= 0:
        return None
    return round(current_close / previous_close - 1.0, 6)


def _close_on_or_before(rows: list[dict], target_date: date) -> float | None:
    candidates = [
        float(row["close"])
        for row in rows
        if date.fromisoformat(str(row["date"])) <= target_date
    ]
    if candidates:
        return candidates[-1]
    return float(rows[0]["close"])


def _score_from_return(value: float) -> float:
    return round(max(0.0, min(100.0, 50.0 + value * 100.0)), 2)
