from __future__ import annotations


def build_final_strategy_report(
    version_rows: list[dict],
    walk_forward: dict,
    robustness: dict,
    production_version: str = "V3_TREND_RISK_ADJUSTED",
    candidate_versions: list[str] | None = None,
) -> dict:
    if not version_rows:
        return {
            "production_candidate": None,
            "candidate": None,
            "confidence": 0.0,
            "production_version": production_version,
            "rows": [],
        }
    candidates = candidate_versions or [
        "V6_THEME_BREADTH_SELECTION",
        "V7_STOCK_BREADTH_SELECTION",
        "V8_ADAPTIVE_SELECTION",
        "V9_EXPOSURE_OPTIMIZED",
        "V10_ROBUST_EXPOSURE",
    ]
    available = [row for row in version_rows if str(row.get("version")) in candidates]
    rows = [
        _score_row(row, available or version_rows, walk_forward.get("versions", {}), _robustness_by_version(robustness))
        for row in available
    ]
    rows.sort(key=lambda item: item["production_score_v2"], reverse=True)
    if rows:
        rows[0]["checks"]["highest_score"] = True
        rows[0]["final_rule_pass"] = all(rows[0]["checks"].values())
    candidate = rows[0] if rows else None
    production_candidate = candidate["version"] if candidate and candidate["final_rule_pass"] else None
    return {
        "production_candidate": production_candidate,
        "candidate": candidate["version"] if candidate else None,
        "confidence": round((candidate["production_score_v2"] if candidate else 0.0) / 100.0, 4),
        "production_version": production_version,
        "rows": rows,
        "reason": _reason(candidate, production_candidate),
    }


def _score_row(row: dict, all_rows: list[dict], walk_versions: dict, robustness_versions: dict) -> dict:
    version = str(row.get("version"))
    walk = walk_versions.get(version, {})
    robust = robustness_versions.get(version, {})
    sharpe_score = _relative_positive(row.get("sharpe"), [item.get("sharpe", 0.0) for item in all_rows])
    return_score = _relative_positive(row.get("annual_return"), [item.get("annual_return", 0.0) for item in all_rows])
    drawdown_score = _drawdown_score(row.get("max_drawdown"), all_rows)
    walk_score = float(walk.get("win_rate", 0.0)) * 100.0
    robustness_score = float(robust.get("robustness_score", 0.0))
    production_score = round(
        0.25 * sharpe_score
        + 0.20 * return_score
        + 0.20 * drawdown_score
        + 0.20 * walk_score
        + 0.15 * robustness_score,
        2,
    )
    checks = {
        "highest_score": False,
        "walk_forward_win_rate": float(walk.get("win_rate", 0.0)) >= 0.60,
        "worst_window": float(walk.get("min_alpha", 0.0)) > -5.0,
        "robustness_pass": bool(robust.get("pass")),
    }
    return {
        "version": version,
        "production_score_v2": production_score,
        "annual_return": float(row.get("annual_return", 0.0)),
        "max_drawdown": float(row.get("max_drawdown", 0.0)),
        "sharpe": float(row.get("sharpe", 0.0)),
        "calmar": float(row.get("calmar", 0.0)),
        "walk_forward_win_rate": float(walk.get("win_rate", 0.0)),
        "walk_forward_min_alpha": float(walk.get("min_alpha", 0.0)),
        "robustness_score": robustness_score,
        "robustness_pass": bool(robust.get("pass")),
        "checks": checks,
        "final_rule_pass": False,
    }


def _robustness_by_version(robustness: dict) -> dict:
    return {
        row.get("version"): row
        for row in robustness.get("version_scores", [])
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


def _reason(candidate: dict | None, production_candidate: str | None) -> list[str]:
    if candidate is None:
        return ["No candidate rows available"]
    if production_candidate:
        return [
            f"{production_candidate} has the highest Production Score V2",
            "Walk Forward, worst window, and robustness rules passed",
        ]
    failed = [
        key
        for key, passed in candidate.get("checks", {}).items()
        if not passed
    ]
    return [
        f"{candidate['version']} has the highest Production Score V2 but failed final governance",
        f"Failed checks: {', '.join(failed)}",
    ]
