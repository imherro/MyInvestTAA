from __future__ import annotations

from datetime import date, timedelta

from engine.selection.models import RelativeStrengthScore


WINDOW_WEIGHTS = {
    "return_21d": (21, 0.20),
    "return_63d": (63, 0.30),
    "return_126d": (126, 0.30),
    "return_252d": (252, 0.20),
}


def calculate_relative_strength(
    asset: str,
    asset_history: list[dict],
    benchmark_history: list[dict],
    benchmark: str = "510300",
) -> RelativeStrengthScore:
    windows: dict[str, dict[str, float | None]] = {}
    weighted_excess = 0.0
    active_weight = 0.0
    for label, (days, weight) in WINDOW_WEIGHTS.items():
        asset_return = _lookback_return(asset_history, days)
        benchmark_return = _lookback_return(benchmark_history, days)
        excess = None
        if asset_return is not None and benchmark_return is not None:
            excess = round(asset_return - benchmark_return, 6)
            weighted_excess += excess * weight
            active_weight += weight
        windows[label] = {
            "asset_return": asset_return,
            "benchmark_return": benchmark_return,
            "excess_return": excess,
        }
    normalized_excess = weighted_excess / active_weight if active_weight else 0.0
    strength_score = _score_from_excess(normalized_excess)
    return RelativeStrengthScore(
        asset=asset,
        benchmark=benchmark,
        strength_score=strength_score,
        weighted_excess_return=round(normalized_excess, 6),
        windows=windows,
    )


def _lookback_return(history: list[dict], days: int) -> float | None:
    rows = _sorted_rows(history)
    if len(rows) < 2:
        return None
    current_date = date.fromisoformat(str(rows[-1]["date"]))
    current_close = float(rows[-1]["close"])
    if current_close <= 0:
        return None
    target_date = current_date - timedelta(days=days)
    past = _close_on_or_before(rows, target_date)
    if past is None or past <= 0:
        return None
    return round(current_close / past - 1.0, 6)


def _score_from_excess(excess_return: float) -> float:
    return round(max(0.0, min(100.0, 50.0 + excess_return * 100.0)), 2)


def _close_on_or_before(rows: list[dict], target_date: date) -> float | None:
    candidates = [
        float(row["close"])
        for row in rows
        if date.fromisoformat(str(row["date"])) <= target_date
    ]
    if candidates:
        return candidates[-1]
    return float(rows[0]["close"])


def _sorted_rows(history: list[dict]) -> list[dict]:
    return sorted(history, key=lambda item: str(item["date"]))
