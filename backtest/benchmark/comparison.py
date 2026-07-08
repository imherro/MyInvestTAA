from __future__ import annotations

from backtest.benchmark.strategies import (
    run_buy_hold_backtest,
    run_classic_saa_backtest,
    run_equal_weight_backtest,
    run_fixed_weight_backtest,
)
from backtest.taa import run_taa_backtest
from engine.asset_repository import load_assets, load_price_histories


def compare_strategies(
    assets: list[dict] | None = None,
    price_history: dict[str, list[dict]] | None = None,
    initial_capital: float = 1.0,
    transaction_cost: float = 0.0,
    cash_return: float = 0.0,
    slippage: float = 0.0,
    expense_ratio: float = 0.0,
) -> dict:
    if assets is None:
        assets = load_assets()
    if price_history is None:
        price_history = load_price_histories()

    taa_result = run_taa_backtest(
        assets=assets,
        price_history=price_history,
        initial_capital=initial_capital,
        transaction_cost=transaction_cost,
        cash_return=cash_return,
        slippage=slippage,
        expense_ratio=expense_ratio,
    )
    benchmarks = [
        run_buy_hold_backtest(
            assets=assets,
            price_history=price_history,
            initial_capital=initial_capital,
        ),
        run_fixed_weight_backtest(
            assets=assets,
            price_history=price_history,
            initial_capital=initial_capital,
            cash_annual_return=cash_return,
        ),
        run_classic_saa_backtest(
            assets=assets,
            price_history=price_history,
            initial_capital=initial_capital,
        ),
        run_equal_weight_backtest(
            assets=assets,
            price_history=price_history,
            initial_capital=initial_capital,
        ),
    ]

    rows = [_strategy_row("MyInvestTAA", "MyInvestTAA", "Dynamic TAA strategy.", taa_result["metrics"])]
    comparisons: dict[str, dict] = {}
    for benchmark in benchmarks:
        alpha = calculate_alpha_metrics(taa_result["metrics"], benchmark["metrics"])
        comparisons[benchmark["strategy_id"]] = alpha
        rows.append(
            _strategy_row(
                benchmark["strategy_id"],
                benchmark["name"],
                benchmark["description"],
                benchmark["metrics"],
                alpha,
                benchmark["weights"],
            )
        )

    return {
        "base_strategy": "MyInvestTAA",
        "period": taa_result["period"],
        "strategies": {row["strategy_id"]: row for row in rows},
        "rows": rows,
        "alpha": comparisons,
        "equity_curves": {
            "MyInvestTAA": taa_result["equity_curve"],
            **{benchmark["strategy_id"]: benchmark["equity_curve"] for benchmark in benchmarks},
        },
        "drawdown_curves": {
            "MyInvestTAA": taa_result["drawdown_curve"],
            **{benchmark["strategy_id"]: benchmark["drawdown_curve"] for benchmark in benchmarks},
        },
    }


def calculate_alpha_metrics(taa_metrics: dict, benchmark_metrics: dict) -> dict:
    taa_return = float(taa_metrics.get("annual_return", 0.0))
    benchmark_return = float(benchmark_metrics.get("annual_return", 0.0))
    taa_drawdown = float(taa_metrics.get("max_drawdown", 0.0))
    benchmark_drawdown = float(benchmark_metrics.get("max_drawdown", 0.0))
    taa_sharpe = float(taa_metrics.get("sharpe", 0.0))
    benchmark_sharpe = float(benchmark_metrics.get("sharpe", 0.0))

    return {
        "excess_return": round(taa_return - benchmark_return, 4),
        "drawdown_improvement": round(abs(benchmark_drawdown) - abs(taa_drawdown), 4),
        "sharpe_difference": round(taa_sharpe - benchmark_sharpe, 4),
        "ending_value_difference": round(
            float(taa_metrics.get("ending_value", 0.0))
            - float(benchmark_metrics.get("ending_value", 0.0)),
            4,
        ),
    }


def _strategy_row(
    strategy_id: str,
    name: str,
    description: str,
    metrics: dict,
    alpha: dict | None = None,
    weights: dict[str, float] | None = None,
) -> dict:
    alpha = alpha or {
        "excess_return": 0.0,
        "drawdown_improvement": 0.0,
        "sharpe_difference": 0.0,
        "ending_value_difference": 0.0,
    }
    return {
        "strategy_id": strategy_id,
        "name": name,
        "description": description,
        "weights": weights or {},
        "annual_return": metrics.get("annual_return", 0.0),
        "max_drawdown": metrics.get("max_drawdown", 0.0),
        "sharpe": metrics.get("sharpe", 0.0),
        "ending_value": metrics.get("ending_value", 0.0),
        **alpha,
    }
