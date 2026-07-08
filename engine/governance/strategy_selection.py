from __future__ import annotations


def build_strategy_selection_report(
    version_rows: list[dict],
    walk_forward: dict,
    production_version: str = "V3_TREND_RISK_ADJUSTED",
) -> dict:
    if not version_rows:
        return {"winner": None, "confidence": 0.0, "rows": [], "production_version": production_version}
    rows = [_score_row(row, version_rows, walk_forward.get("versions", {})) for row in version_rows]
    winner = max(rows, key=lambda item: (item["production_score"], item["sharpe"], item["annual_return"]))
    return {
        "winner": winner["version"],
        "confidence": round(winner["production_score"] / 100.0, 4),
        "production_version": production_version,
        "rows": sorted(rows, key=lambda item: item["production_score"], reverse=True),
    }


def _score_row(row: dict, all_rows: list[dict], walk_versions: dict) -> dict:
    version = str(row.get("version"))
    sharpe_score = _relative_positive(row.get("sharpe"), [item.get("sharpe", 0.0) for item in all_rows])
    drawdown_score = _drawdown_score(row.get("max_drawdown"), all_rows)
    calmar_score = _relative_positive(row.get("calmar"), [item.get("calmar", 0.0) for item in all_rows])
    walk = walk_versions.get(version, {})
    win_rate_score = float(walk.get("win_rate", 0.0)) * 100.0
    stability_score = _stability_score(walk)
    production_score = round(
        0.30 * sharpe_score
        + 0.25 * win_rate_score
        + 0.20 * drawdown_score
        + 0.15 * calmar_score
        + 0.10 * stability_score,
        2,
    )
    return {
        "version": version,
        "production_score": production_score,
        "annual_return": float(row.get("annual_return", 0.0)),
        "max_drawdown": float(row.get("max_drawdown", 0.0)),
        "sharpe": float(row.get("sharpe", 0.0)),
        "calmar": float(row.get("calmar", 0.0)),
        "walk_forward_win_rate": float(walk.get("win_rate", 0.0)),
        "walk_forward_avg_alpha": float(walk.get("avg_alpha", 0.0)),
        "walk_forward_min_alpha": float(walk.get("min_alpha", 0.0)),
        "stability_score": stability_score,
    }


def _relative_positive(value: object, values: list[object]) -> float:
    clean = [max(0.0, float(item or 0.0)) for item in values]
    peak = max(clean, default=0.0)
    if peak <= 0:
        return 0.0
    return round(max(0.0, float(value or 0.0)) / peak * 100.0, 4)


def _drawdown_score(value: object, rows: list[dict]) -> float:
    drawdowns = [abs(float(row.get("max_drawdown", 0.0))) for row in rows]
    worst = max(drawdowns, default=0.0)
    if worst <= 0:
        return 100.0
    current = abs(float(value or 0.0))
    return round(max(0.0, 100.0 * (1.0 - current / worst)), 4)


def _stability_score(walk: dict) -> float:
    if not walk:
        return 0.0
    win_rate = float(walk.get("win_rate", 0.0))
    drawdown_rate = float(walk.get("drawdown_pass_rate", 0.0))
    min_alpha = float(walk.get("min_alpha", 0.0))
    collapse_penalty = 25.0 if min_alpha < -5.0 else 0.0
    return round(max(0.0, (0.5 * win_rate + 0.5 * drawdown_rate) * 100.0 - collapse_penalty), 4)
