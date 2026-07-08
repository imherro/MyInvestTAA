from __future__ import annotations


def decompose_excess_return_v3(strategy_result: dict, benchmark_row: dict | None) -> dict:
    strategy_metrics = strategy_result.get("metrics", {})
    strategy_return = float(strategy_metrics.get("annual_return", 0.0))
    benchmark_return = float((benchmark_row or {}).get("annual_return", 0.0))
    excess = round(strategy_return - benchmark_return, 4)
    exposure_gap = _average_exposure(strategy_result) - _benchmark_equity_exposure(benchmark_row)
    timing = round(exposure_gap / 100.0 * benchmark_return, 4)
    strategy_drawdown = abs(float(strategy_metrics.get("max_drawdown", 0.0)))
    benchmark_drawdown = abs(float((benchmark_row or {}).get("max_drawdown", 0.0)))
    allocation = round((benchmark_drawdown - strategy_drawdown) * 0.05, 4)
    selection = round(excess - timing - allocation, 4)
    return {
        "strategy": strategy_result.get("strategy", "MyInvestTAA"),
        "benchmark": (benchmark_row or {}).get("strategy_id", "UNKNOWN"),
        "excess_return": excess,
        "allocation": allocation,
        "selection": selection,
        "timing": timing,
        "interaction": 0.0,
        "check_sum": round(allocation + selection + timing, 4),
    }


def _average_exposure(strategy_result: dict) -> float:
    states = strategy_result.get("states", [])
    if not states:
        return 0.0
    exposures = [
        100.0 - float(state.get("weights", {}).get("CASH", 0.0))
        for state in states
    ]
    return sum(exposures) / len(exposures)


def _benchmark_equity_exposure(benchmark_row: dict | None) -> float:
    weights = (benchmark_row or {}).get("weights") or {}
    return sum(
        float(weight)
        for asset_id, weight in weights.items()
        if asset_id != "CASH"
    )
