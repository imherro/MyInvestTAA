from __future__ import annotations

from backtest.research.metrics import build_metrics


HS300_RESEARCH_ASSET_ID = "H00300.CSI"


def build_research_benchmarks(
    aligned: dict,
    *,
    start_index: int,
    strategy_metrics: dict,
) -> dict:
    """Build research-only benchmarks on the same aligned index-price sample."""
    dates = aligned.get("dates", [])
    prices = aligned.get("prices", {})
    if start_index >= len(dates):
        return {"available": False, "rows": [], "alpha": {}, "warnings": ["benchmark start is outside aligned price data"]}

    rows = [
        {"strategy": "RESEARCH_TAA_MVP", **strategy_metrics},
    ]
    warnings: list[str] = []

    hs300_prices = prices.get(HS300_RESEARCH_ASSET_ID)
    if hs300_prices:
        hs300_curve = _buy_hold_curve(dates, hs300_prices, start_index)
        rows.append({"strategy": "HS300_RESEARCH_BUY_HOLD", **build_metrics(hs300_curve)})
    else:
        hs300_curve = []
        warnings.append(f"{HS300_RESEARCH_ASSET_ID} is unavailable for benchmark comparison")

    equal_weight_curve = _monthly_equal_weight_curve(dates, prices, start_index)
    if equal_weight_curve:
        rows.append({"strategy": "EQUAL_WEIGHT_RESEARCH", **build_metrics(equal_weight_curve)})
    else:
        warnings.append("eligible research asset prices are unavailable for equal-weight benchmark")

    metrics_by_strategy = {row["strategy"]: row for row in rows}
    alpha = {
        "vs_hs300": _annual_return_delta(strategy_metrics, metrics_by_strategy.get("HS300_RESEARCH_BUY_HOLD")),
        "vs_equal_weight": _annual_return_delta(strategy_metrics, metrics_by_strategy.get("EQUAL_WEIGHT_RESEARCH")),
    }
    return {
        "available": len(rows) > 1,
        "rows": rows,
        "alpha": alpha,
        "warnings": warnings,
    }


def _annual_return_delta(strategy_metrics: dict, benchmark_metrics: dict | None) -> float | None:
    if not benchmark_metrics:
        return None
    return round(float(strategy_metrics.get("annual_return", 0.0)) - float(benchmark_metrics.get("annual_return", 0.0)), 6)


def _buy_hold_curve(dates: list[str], prices: list[float], start_index: int) -> list[dict]:
    start = prices[start_index]
    if start <= 0:
        return []
    return [
        {"date": date, "value": round(price / start, 8)}
        for date, price in zip(dates[start_index:], prices[start_index:])
    ]


def _monthly_equal_weight_curve(dates: list[str], prices: dict[str, list[float]], start_index: int) -> list[dict]:
    asset_ids = sorted(prices)
    if not asset_ids:
        return []
    curve = [{"date": dates[start_index], "value": 1.0}]
    weights = {asset_id: 1.0 / len(asset_ids) for asset_id in asset_ids}
    for index in range(start_index + 1, len(dates)):
        if dates[index][0:7] != dates[index - 1][0:7]:
            weights = {asset_id: 1.0 / len(asset_ids) for asset_id in asset_ids}
        daily_return = sum(
            weights[asset_id] * (prices[asset_id][index] / prices[asset_id][index - 1] - 1.0)
            for asset_id in asset_ids
            if prices[asset_id][index - 1] > 0
        )
        curve.append({"date": dates[index], "value": round(curve[-1]["value"] * (1.0 + daily_return), 8)})
    return curve
