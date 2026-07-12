from __future__ import annotations

from collections import defaultdict

from backtest.research.metrics import build_metrics
from backtest.research.models import ResearchBacktestConfig, ResearchPrice
from backtest.research.universe import validate_research_backtest_inputs


def run_research_backtest(
    assets,
    price_data: dict[str, list[ResearchPrice]],
    *,
    config: ResearchBacktestConfig | None = None,
    readiness_report: dict | None = None,
) -> dict:
    cfg = config or ResearchBacktestConfig()
    validation = validate_research_backtest_inputs(
        assets,
        price_data,
        readiness_report,
        min_assets=cfg.min_assets,
    )
    if not validation["valid"]:
        return {
            "available": False,
            "strategy": cfg.strategy,
            "errors": validation["errors"],
            "excluded_assets": validation["excluded_assets"],
            "unavailable_assets": validation["unavailable_assets"],
            "warnings": validation["warnings"],
        }

    valid_assets = validation["valid_assets"]
    aligned = _aligned_price_rows(valid_assets, price_data)
    if len(aligned["dates"]) <= cfg.lookback_12m + 1:
        return {
            "available": False,
            "strategy": cfg.strategy,
            "errors": ["insufficient price history for 12M research score"],
            "excluded_assets": validation["excluded_assets"],
            "unavailable_assets": validation["unavailable_assets"],
            "warnings": validation["warnings"],
        }

    equity_curve, allocations = _run_monthly_strategy(valid_assets, aligned, cfg)
    metrics = build_metrics(equity_curve)
    return {
        "available": True,
        "strategy": cfg.strategy,
        "universe_count": len(valid_assets),
        "period": {
            "start": equity_curve[0]["date"] if equity_curve else None,
            "end": equity_curve[-1]["date"] if equity_curve else None,
        },
        "metrics": metrics,
        "equity_curve": equity_curve,
        "monthly_allocations": allocations,
        "excluded_assets": validation["excluded_assets"],
        "unavailable_assets": validation["unavailable_assets"],
        "warnings": [
            *validation["warnings"],
            "This research backtest does not replace the current V11 production candidate.",
            "Research backtest does not represent ETF execution returns.",
        ],
    }


def compute_research_scores(
    assets,
    aligned: dict,
    date_index: int,
    config: ResearchBacktestConfig | None = None,
) -> dict[str, dict]:
    cfg = config or ResearchBacktestConfig()
    scores = {}
    for asset in assets:
        series = aligned["prices"][asset.asset_id]
        current = series[date_index]
        price_6m = series[date_index - cfg.lookback_6m]
        price_12m = series[date_index - cfg.lookback_12m]
        if price_6m <= 0 or price_12m <= 0:
            continue
        momentum_6m = current / price_6m - 1.0
        momentum_12m = current / price_12m - 1.0
        drawdown = _window_max_drawdown(series[date_index - cfg.lookback_12m : date_index + 1])
        drawdown_resilience = 1.0 + drawdown
        score = (
            cfg.momentum_6m_weight * momentum_6m
            + cfg.momentum_12m_weight * momentum_12m
            + cfg.drawdown_resilience_weight * drawdown_resilience
        )
        scores[asset.asset_id] = {
            "asset_id": asset.asset_id,
            "score": round(score, 8),
            "momentum_6m": round(momentum_6m, 8),
            "momentum_12m": round(momentum_12m, 8),
            "drawdown_resilience": round(drawdown_resilience, 8),
        }
    return scores


def apply_weight_constraints(selected_assets, config: ResearchBacktestConfig | None = None) -> dict[str, float]:
    cfg = config or ResearchBacktestConfig()
    if not selected_assets:
        return {"CASH": 1.0}

    base_weight = 1.0 / len(selected_assets)
    weights = {}
    theme_total = 0.0
    for asset in selected_assets:
        cap = cfg.single_asset_max
        if asset.sleeve == "theme" or asset.category == "theme":
            remaining_theme = max(cfg.theme_sleeve_max - theme_total, 0.0)
            cap = min(cap, cfg.single_theme_max, remaining_theme)
        weight = min(base_weight, cap)
        weights[asset.asset_id] = weight
        if asset.sleeve == "theme" or asset.category == "theme":
            theme_total += weight

    leftover = max(1.0 - sum(weights.values()), 0.0)
    weights = _redistribute_leftover(weights, selected_assets, leftover, cfg)
    cash = max(1.0 - sum(weights.values()), 0.0)
    if cash > 1e-8:
        weights["CASH"] = round(cash, 10)
    return {asset_id: round(weight, 10) for asset_id, weight in weights.items() if weight > 1e-10}


def _run_monthly_strategy(assets, aligned: dict, cfg: ResearchBacktestConfig) -> tuple[list[dict], list[dict]]:
    dates = aligned["dates"]
    asset_by_id = {asset.asset_id: asset for asset in assets}
    allocations = []
    equity_curve = [{"date": dates[cfg.lookback_12m], "value": 1.0}]
    current_weights: dict[str, float] = {"CASH": 1.0}

    for index in range(cfg.lookback_12m + 1, len(dates)):
        date = dates[index]
        previous_date = dates[index - 1]
        if _is_rebalance_date(dates, index):
            scores = compute_research_scores(assets, aligned, index - 1, cfg)
            selected_ids = [
                row["asset_id"]
                for row in sorted(scores.values(), key=lambda item: item["score"], reverse=True)[: cfg.top_n]
            ]
            selected_assets = [asset_by_id[asset_id] for asset_id in selected_ids]
            current_weights = apply_weight_constraints(selected_assets, cfg)
            allocations.append(
                {
                    "date": previous_date,
                    "weights": current_weights,
                    "scores": {asset_id: scores[asset_id] for asset_id in selected_ids},
                }
            )

        daily_return = _portfolio_return(current_weights, aligned["prices"], dates, index)
        equity_curve.append(
            {
                "date": date,
                "value": round(equity_curve[-1]["value"] * (1.0 + daily_return), 8),
            }
        )

    return equity_curve, allocations


def _aligned_price_rows(assets, price_data: dict[str, list[ResearchPrice]]) -> dict:
    date_sets = []
    by_asset = {}
    for asset in assets:
        rows = sorted(price_data.get(asset.asset_id, []), key=lambda row: row.date)
        by_asset[asset.asset_id] = {row.date: row.close for row in rows}
        date_sets.append(set(by_asset[asset.asset_id]))
    common_dates = sorted(set.intersection(*date_sets)) if date_sets else []
    prices = {
        asset.asset_id: [by_asset[asset.asset_id][date] for date in common_dates]
        for asset in assets
    }
    return {"dates": common_dates, "prices": prices}


def _portfolio_return(weights: dict[str, float], prices: dict[str, list[float]], dates: list[str], index: int) -> float:
    total = 0.0
    for asset_id, weight in weights.items():
        if asset_id == "CASH":
            continue
        previous = prices[asset_id][index - 1]
        current = prices[asset_id][index]
        if previous > 0:
            total += weight * (current / previous - 1.0)
    return total


def _is_rebalance_date(dates: list[str], index: int) -> bool:
    return dates[index][0:7] != dates[index - 1][0:7]


def _window_max_drawdown(values: list[float]) -> float:
    peak = None
    worst = 0.0
    for value in values:
        peak = value if peak is None else max(peak, value)
        if peak:
            worst = min(worst, value / peak - 1.0)
    return worst


def _redistribute_leftover(weights: dict[str, float], selected_assets, leftover: float, cfg: ResearchBacktestConfig) -> dict[str, float]:
    if leftover <= 1e-10:
        return weights
    non_theme = [asset for asset in selected_assets if asset.sleeve != "theme" and asset.category != "theme"]
    while leftover > 1e-10 and non_theme:
        capacity_by_asset = {
            asset.asset_id: max(cfg.single_asset_max - weights.get(asset.asset_id, 0.0), 0.0)
            for asset in non_theme
        }
        available = [asset_id for asset_id, capacity in capacity_by_asset.items() if capacity > 1e-10]
        if not available:
            break
        addition = leftover / len(available)
        spent = 0.0
        for asset_id in available:
            add = min(addition, capacity_by_asset[asset_id])
            weights[asset_id] = weights.get(asset_id, 0.0) + add
            spent += add
        if spent <= 1e-10:
            break
        leftover -= spent
    return weights
