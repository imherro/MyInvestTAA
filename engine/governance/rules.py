from __future__ import annotations


def evaluate_promotion(
    version: str,
    version_metrics: dict,
    benchmark_metrics: dict | None = None,
    walk_forward: dict | None = None,
    min_win_rate: float = 0.6,
    min_windows: int = 3,
) -> dict:
    benchmark_metrics = benchmark_metrics or {}
    walk_forward = walk_forward or {}
    checks = {
        "sharpe_beats_benchmark": _float(version_metrics.get("sharpe")) > _float(benchmark_metrics.get("sharpe")),
        "drawdown_not_worse": abs(_float(version_metrics.get("max_drawdown"))) <= abs(_float(benchmark_metrics.get("max_drawdown"))),
        "return_not_worse": _float(version_metrics.get("annual_return")) >= _float(benchmark_metrics.get("annual_return")),
        "walk_forward_present": int(walk_forward.get("windows", 0)) >= min_windows,
        "walk_forward_win_rate": _float(walk_forward.get("win_rate")) >= min_win_rate,
        "walk_forward_drawdown": _float(walk_forward.get("drawdown_pass_rate")) >= min_win_rate,
    }
    reasons = _failure_reasons(checks)
    promotion_score = round(100.0 * sum(1 for passed in checks.values() if passed) / len(checks), 2)
    promotion = all(checks.values())
    return {
        "version": version,
        "promotion": promotion,
        "approval_status": "approved" if promotion else "pending",
        "promotion_score": promotion_score,
        "validation_windows": int(walk_forward.get("windows", 0)),
        "win_rate": _float(walk_forward.get("win_rate")),
        "avg_alpha": _float(walk_forward.get("avg_alpha")),
        "reasons": ["Promotion rule passed"] if promotion else reasons,
        "checks": checks,
    }


def build_promotion_report(
    version_rows: list[dict],
    walk_forward: dict,
    benchmark_version: str = "V3_TREND_RISK_ADJUSTED",
    candidate_versions: list[str] | None = None,
) -> dict:
    candidates = candidate_versions or ["V6_THEME_BREADTH_SELECTION", "V7_STOCK_BREADTH_SELECTION"]
    by_version = {str(row.get("version")): row for row in version_rows}
    benchmark = by_version.get(benchmark_version, {})
    wf_versions = walk_forward.get("versions", {})
    rows = [
        evaluate_promotion(
            version,
            by_version.get(version, {}),
            benchmark_metrics=benchmark,
            walk_forward=wf_versions.get(version, {}),
        )
        for version in candidates
        if version in by_version
    ]
    best = None
    if rows:
        best = max(rows, key=lambda item: (item["promotion"], item["promotion_score"], item["avg_alpha"]))["version"]
    return {
        "benchmark": benchmark_version,
        "rows": rows,
        "best_candidate": best,
        "approved_versions": [row["version"] for row in rows if row["promotion"]],
    }


def _failure_reasons(checks: dict[str, bool]) -> list[str]:
    labels = {
        "sharpe_beats_benchmark": "Sharpe does not beat benchmark",
        "drawdown_not_worse": "Max drawdown is worse than benchmark",
        "return_not_worse": "Annual return is below benchmark",
        "walk_forward_present": "rolling validation missing",
        "walk_forward_win_rate": "Walk-forward win rate below threshold",
        "walk_forward_drawdown": "Walk-forward drawdown pass rate below threshold",
    }
    return [label for key, label in labels.items() if not checks.get(key)]


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
