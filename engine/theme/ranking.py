from __future__ import annotations

from engine.theme.mapping import theme_for_asset
from engine.theme.momentum import calculate_theme_momentum
from engine.theme.models import ThemeMomentumScore


def rank_theme_momentum(histories: dict[str, list[dict]]) -> list[dict]:
    by_theme: dict[str, dict[str, list[dict]]] = {}
    for asset_id, history in histories.items():
        by_theme.setdefault(theme_for_asset(asset_id), {})[asset_id] = history
    scores = [
        calculate_theme_momentum(theme, member_histories)
        for theme, member_histories in by_theme.items()
    ]
    ranked = sorted(scores, key=lambda item: item.weighted_return, reverse=True)
    return [
        _ranked_row(score, index, len(ranked))
        for index, score in enumerate(ranked)
    ]


def theme_momentum_by_theme(histories: dict[str, list[dict]]) -> dict[str, dict]:
    return {row["theme"]: row for row in rank_theme_momentum(histories)}


def _ranked_row(score: ThemeMomentumScore, index: int, count: int) -> dict:
    if count <= 1:
        percentile = 100.0
    else:
        percentile = round(100.0 * (count - index - 1) / (count - 1), 2)
    row = score.as_dict()
    row["rank"] = index + 1
    row["raw_momentum_score"] = row["momentum_score"]
    row["momentum_score"] = percentile
    return row
