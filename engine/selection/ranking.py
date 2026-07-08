from __future__ import annotations

from engine.selection.models import RelativeStrengthScore
from engine.selection.relative_strength import calculate_relative_strength


def rank_relative_strength(
    histories: dict[str, list[dict]],
    benchmark_id: str = "510300",
) -> list[dict]:
    benchmark_history = histories.get(benchmark_id, [])
    scores = [
        calculate_relative_strength(asset_id, history, benchmark_history, benchmark=benchmark_id)
        for asset_id, history in histories.items()
        if len(history) >= 2
    ]
    ranked = sorted(scores, key=lambda item: item.weighted_excess_return, reverse=True)
    return [
        _ranked_row(score, index, len(ranked))
        for index, score in enumerate(ranked)
    ]


def _ranked_row(score: RelativeStrengthScore, index: int, count: int) -> dict:
    if count <= 1:
        percentile_score = 100.0
    else:
        percentile_score = round(100.0 * (count - index - 1) / (count - 1), 2)
    row = score.as_dict()
    row["rank"] = index + 1
    row["strength_score"] = percentile_score
    row["raw_strength_score"] = score.strength_score
    return row
