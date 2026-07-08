from __future__ import annotations

from datetime import date

from backtest.benchmark.models import (
    BenchmarkResult,
    BenchmarkStrategy,
    normalize_benchmark_weights,
)
from backtest.metrics import annual_return, max_drawdown, sharpe_ratio
from backtest.taa.metrics import drawdown_curve
from engine.asset_repository import load_assets, load_price_histories


def run_buy_hold_backtest(
    asset_id: str = "510300",
    assets: list[dict] | None = None,
    price_history: dict[str, list[dict]] | None = None,
    initial_capital: float = 1.0,
) -> dict:
    assets_by_id = _assets_by_id(assets)
    if asset_id not in assets_by_id:
        raise ValueError(f"unknown asset_id: {asset_id}")
    asset_name = assets_by_id[asset_id]["name"]
    strategy = BenchmarkStrategy(
        strategy_id="HS300_BUY_HOLD" if asset_id == "510300" else f"BUY_HOLD_{asset_id}",
        name=f"{asset_name} Buy & Hold",
        weights={asset_id: 100.0},
        description="Single-asset passive buy-and-hold benchmark.",
    )
    return _run_static_weight_backtest(
        strategy,
        price_history=price_history,
        initial_capital=initial_capital,
    ).as_dict()


def run_fixed_weight_backtest(
    equity_asset_id: str = "510300",
    equity_weight: float = 60.0,
    cash_weight: float = 40.0,
    assets: list[dict] | None = None,
    price_history: dict[str, list[dict]] | None = None,
    initial_capital: float = 1.0,
    cash_annual_return: float = 0.015,
) -> dict:
    assets_by_id = _assets_by_id(assets)
    if equity_asset_id not in assets_by_id:
        raise ValueError(f"unknown asset_id: {equity_asset_id}")
    strategy = BenchmarkStrategy(
        strategy_id="SAA_60_40",
        name="60/40 Equity Cash",
        weights={equity_asset_id: equity_weight, "CASH": cash_weight},
        description="Static strategic allocation benchmark with equity and cash.",
    )
    return _run_static_weight_backtest(
        strategy,
        price_history=price_history,
        initial_capital=initial_capital,
        cash_annual_return=cash_annual_return,
    ).as_dict()


def run_equal_weight_backtest(
    asset_ids: list[str] | None = None,
    assets: list[dict] | None = None,
    price_history: dict[str, list[dict]] | None = None,
    initial_capital: float = 1.0,
) -> dict:
    if assets is None:
        assets = load_assets()
    if asset_ids is None:
        asset_ids = [asset["id"] for asset in assets]
    if not asset_ids:
        return _empty_result(
            BenchmarkStrategy(
                strategy_id="EQUAL_WEIGHT",
                name="Equal Weight ETF",
                weights={"CASH": 100.0},
                description="Equal-weight ETF benchmark.",
            ),
            initial_capital,
        ).as_dict()

    assets_by_id = _assets_by_id(assets)
    missing = sorted(set(asset_ids) - set(assets_by_id))
    if missing:
        raise ValueError(f"unknown asset_id: {missing[0]}")

    weight = 100.0 / len(asset_ids)
    strategy = BenchmarkStrategy(
        strategy_id="EQUAL_WEIGHT",
        name="Equal Weight ETF",
        weights={asset_id: weight for asset_id in asset_ids},
        description="Equal-weight passive ETF basket benchmark.",
    )
    return _run_static_weight_backtest(
        strategy,
        price_history=price_history,
        initial_capital=initial_capital,
    ).as_dict()


def _run_static_weight_backtest(
    strategy: BenchmarkStrategy,
    price_history: dict[str, list[dict]] | None = None,
    initial_capital: float = 1.0,
    cash_annual_return: float = 0.0,
) -> BenchmarkResult:
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if price_history is None:
        price_history = load_price_histories()

    weights = normalize_benchmark_weights(strategy.weights)
    strategy = BenchmarkStrategy(
        strategy_id=strategy.strategy_id,
        name=strategy.name,
        weights=weights,
        description=strategy.description,
    )
    _validate_history_coverage(weights, price_history)
    dates = _all_dates_for_weights(weights, price_history)
    if len(dates) < 2:
        return _empty_result(strategy, initial_capital)

    monthly_cash_return = (1.0 + cash_annual_return) ** (1.0 / 12.0) - 1.0
    value = initial_capital
    values = [value]
    returns: list[float] = []

    for previous_date, current_date in zip(dates, dates[1:]):
        period_return = _static_portfolio_return(
            weights,
            price_history,
            previous_date,
            current_date,
            monthly_cash_return,
        )
        returns.append(period_return)
        value = value * (1.0 + period_return)
        values.append(value)

    metric_values = {
        "annual_return": annual_return(values, periods_per_year=12),
        "max_drawdown": max_drawdown(values),
        "sharpe": sharpe_ratio(returns, periods_per_year=12),
        "ending_value": round(values[-1], 4),
    }
    return BenchmarkResult(
        strategy=strategy,
        period={"start": dates[0].isoformat(), "end": dates[-1].isoformat(), "rows": len(dates)},
        metrics=metric_values,
        equity_curve=[
            {"date": item_date.isoformat(), "value": round(item_value, 4)}
            for item_date, item_value in zip(dates, values)
        ],
        drawdown_curve=[
            {"date": item_date.isoformat(), "drawdown_pct": drawdown}
            for item_date, drawdown in zip(dates, drawdown_curve(values))
        ],
    )


def _assets_by_id(assets: list[dict] | None) -> dict[str, dict]:
    if assets is None:
        assets = load_assets()
    return {asset["id"]: asset for asset in assets}


def _validate_history_coverage(weights: dict[str, float], price_history: dict[str, list[dict]]) -> None:
    missing = [
        asset_id
        for asset_id in weights
        if asset_id != "CASH" and asset_id not in price_history
    ]
    if missing:
        raise ValueError(f"history not found for asset_id: {missing[0]}")


def _all_dates_for_weights(weights: dict[str, float], price_history: dict[str, list[dict]]) -> list[date]:
    asset_dates = {
        date.fromisoformat(str(row["date"]))
        for asset_id in weights
        if asset_id != "CASH"
        for row in price_history.get(asset_id, [])
    }
    return sorted(asset_dates)


def _static_portfolio_return(
    weights: dict[str, float],
    price_history: dict[str, list[dict]],
    previous_date: date,
    current_date: date,
    monthly_cash_return: float,
) -> float:
    result = 0.0
    for asset_id, weight in weights.items():
        if asset_id == "CASH":
            result += (weight / 100.0) * monthly_cash_return
            continue
        previous_close = _close_on_or_before(price_history[asset_id], previous_date)
        current_close = _close_on_or_before(price_history[asset_id], current_date)
        if previous_close is None or current_close is None:
            continue
        result += (weight / 100.0) * (current_close / previous_close - 1.0)
    return result


def _close_on_or_before(history: list[dict], target: date) -> float | None:
    close = None
    for row in history:
        row_date = date.fromisoformat(str(row["date"]))
        if row_date <= target:
            close = float(row["close"])
        else:
            break
    return close


def _empty_result(strategy: BenchmarkStrategy, initial_capital: float) -> BenchmarkResult:
    return BenchmarkResult(
        strategy=strategy,
        period=None,
        metrics={
            "annual_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "ending_value": round(initial_capital, 4),
        },
        equity_curve=[],
        drawdown_curve=[],
    )
