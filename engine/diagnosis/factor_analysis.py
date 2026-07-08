from __future__ import annotations


def decompose_vs_static(strategy_result: dict, static_row: dict | None) -> dict:
    metrics = strategy_result.get("metrics", {})
    strategy_return = float(metrics.get("annual_return", 0.0))
    strategy_drawdown = float(metrics.get("max_drawdown", 0.0))
    benchmark_return = float((static_row or {}).get("annual_return", 0.0))
    benchmark_drawdown = float((static_row or {}).get("max_drawdown", 0.0))
    exposure_gap = _average_exposure(strategy_result) - 60.0
    return_gap = round(strategy_return - benchmark_return, 4)
    drawdown_improvement = round(abs(benchmark_drawdown) - abs(strategy_drawdown), 4)
    timing_contribution = round(return_gap * 0.6, 4)
    selection_contribution = round(return_gap - timing_contribution, 4)
    return {
        "strategy": strategy_result.get("strategy", "MyInvestTAA"),
        "benchmark": (static_row or {}).get("strategy_id", "UNKNOWN"),
        "return_gap": return_gap,
        "drawdown_improvement": drawdown_improvement,
        "market_exposure_gap": round(exposure_gap, 4),
        "timing_contribution": timing_contribution,
        "selection_contribution": selection_contribution,
    }


def compare_strategy_versions(results: dict[str, dict]) -> dict:
    rows = []
    for version, result in results.items():
        metrics = result.get("metrics", {})
        rows.append(
            {
                "version": version,
                "annual_return": metrics.get("annual_return", 0.0),
                "max_drawdown": metrics.get("max_drawdown", 0.0),
                "sharpe": metrics.get("sharpe", 0.0),
                "calmar": metrics.get("calmar", 0.0),
                "ending_value": metrics.get("ending_value", 0.0),
            }
        )
    best = None
    if rows:
        best = max(rows, key=lambda item: (item["sharpe"], item["annual_return"]))["version"]
    return {"rows": rows, "best_version": best}


def _average_exposure(strategy_result: dict) -> float:
    states = strategy_result.get("states", [])
    if not states:
        return 0.0
    exposures = [
        100.0 - float(state.get("weights", {}).get("CASH", 0.0))
        for state in states
    ]
    return sum(exposures) / len(exposures)
