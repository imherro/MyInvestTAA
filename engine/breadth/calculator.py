from __future__ import annotations

from engine.breadth.models import BreadthScore
from engine.theme.mapping import theme_for_asset


def calculate_theme_breadth(theme: str, member_histories: dict[str, list[dict]]) -> BreadthScore:
    advancers = 0
    new_highs = 0
    above_ma = 0
    total = 0
    for history in member_histories.values():
        rows = sorted(history, key=lambda item: str(item["date"]))
        if len(rows) < 2:
            continue
        current = float(rows[-1]["close"])
        previous = float(rows[-2]["close"])
        sample = [float(row["close"]) for row in rows[-12:]]
        ma_sample = [float(row["close"]) for row in rows[-6:]]
        total += 1
        advancers += 1 if current > previous else 0
        new_highs += 1 if current >= max(sample) else 0
        above_ma += 1 if current >= sum(ma_sample) / len(ma_sample) else 0
    advancer_ratio = _ratio(advancers, total)
    new_high_ratio = _ratio(new_highs, total)
    above_ma_ratio = _ratio(above_ma, total)
    breadth_score = round(40.0 * advancer_ratio + 30.0 * new_high_ratio + 30.0 * above_ma_ratio, 2)
    return BreadthScore(
        theme=theme,
        breadth_score=breadth_score,
        advancers=advancers,
        total=total,
        advancer_ratio=advancer_ratio,
        new_high_ratio=new_high_ratio,
        above_ma_ratio=above_ma_ratio,
    )


def rank_theme_breadth(histories: dict[str, list[dict]]) -> list[dict]:
    by_theme: dict[str, dict[str, list[dict]]] = {}
    for asset_id, history in histories.items():
        by_theme.setdefault(theme_for_asset(asset_id), {})[asset_id] = history
    rows = [
        calculate_theme_breadth(theme, member_histories).as_dict()
        for theme, member_histories in by_theme.items()
    ]
    return sorted(rows, key=lambda item: item["breadth_score"], reverse=True)


def theme_breadth_by_theme(histories: dict[str, list[dict]]) -> dict[str, dict]:
    return {row["theme"]: row for row in rank_theme_breadth(histories)}


def _ratio(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0
