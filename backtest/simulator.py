from __future__ import annotations

from backtest.metrics import annual_return, max_drawdown, sharpe_ratio
from engine.asset_repository import load_assets, load_price_history


def run_sample_backtest(asset_id: str = "512890", weight: float = 0.6) -> dict:
    assets = {asset["id"]: asset for asset in load_assets()}
    if asset_id not in assets:
        raise ValueError(f"unknown asset_id: {asset_id}")

    history = load_price_history(asset_id)
    result = simulate_weighted_buy_hold(history, weight=weight)
    result.update(
        {
            "asset_id": asset_id,
            "asset_name": assets[asset_id]["name"],
            "signal": "sample_drawdown_anchor_weight",
            "weight": weight,
        }
    )
    return result


def simulate_weighted_buy_hold(price_series: list[dict], weight: float) -> dict:
    if not 0 <= weight <= 1:
        raise ValueError("weight must be between 0 and 1")
    if len(price_series) < 2:
        raise ValueError("price_series must contain at least two rows")

    closes = [float(row["close"]) for row in price_series]
    returns: list[float] = []
    equity_curve = [1.0]

    for previous, current in zip(closes, closes[1:]):
        asset_return = current / previous - 1.0
        portfolio_return = asset_return * weight
        returns.append(portfolio_return)
        equity_curve.append(equity_curve[-1] * (1.0 + portfolio_return))

    return {
        "period": {
            "start": price_series[0]["date"],
            "end": price_series[-1]["date"],
            "rows": len(price_series),
        },
        "annual_return": annual_return(equity_curve, periods_per_year=12),
        "max_drawdown": max_drawdown(equity_curve),
        "sharpe": sharpe_ratio(returns, periods_per_year=12),
        "ending_value": round(equity_curve[-1], 4),
    }

