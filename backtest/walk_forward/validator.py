from __future__ import annotations

from datetime import date

from backtest.taa import run_taa_backtest
from backtest.taa.metrics import calculate_taa_metrics


DEFAULT_WALK_FORWARD_SPECS = [
    {
        "version": "V3_TREND_RISK_ADJUSTED",
        "score_version": "v4",
        "max_weight_step": 10.0,
        "volatility_adjustment": True,
    },
    {
        "version": "V6_THEME_BREADTH_SELECTION",
        "score_version": "v6",
        "max_weight_step": 10.0,
        "volatility_adjustment": True,
    },
    {
        "version": "V7_STOCK_BREADTH_SELECTION",
        "score_version": "v7",
        "max_weight_step": 10.0,
        "volatility_adjustment": True,
    },
]


def run_walk_forward_validation(
    assets: list[dict],
    price_history: dict[str, list[dict]],
    stock_price_history: dict[str, list[dict]] | None = None,
    common_kwargs: dict | None = None,
    version_specs: list[dict] | None = None,
    benchmark_version: str = "V3_TREND_RISK_ADJUSTED",
    train_years: int = 3,
    test_years: int = 1,
) -> dict:
    if train_years <= 0:
        raise ValueError("train_years must be positive")
    if test_years <= 0:
        raise ValueError("test_years must be positive")

    dates = _all_dates(price_history)
    if len(dates) < 2:
        return _empty_report(benchmark_version, train_years, test_years)

    specs = version_specs or DEFAULT_WALK_FORWARD_SPECS
    kwargs = dict(common_kwargs or {})
    rows: list[dict] = []
    start_year = dates[0].year + train_years
    end_year = dates[-1].year
    for test_year in range(start_year, end_year + 1, test_years):
        train_start = date(test_year - train_years, 1, 1)
        test_start = date(test_year, 1, 1)
        test_end = min(date(test_year + test_years - 1, 12, 31), dates[-1])
        if test_start > dates[-1]:
            continue
        window_histories = _filter_histories(price_history, train_start, test_end)
        window_stock_histories = _filter_histories(stock_price_history or {}, train_start, test_end)
        results = {
            spec["version"]: run_taa_backtest(
                assets=assets,
                price_history=window_histories,
                stock_price_history=window_stock_histories,
                **kwargs,
                **_taa_kwargs(spec),
            )
            for spec in specs
        }
        benchmark_metrics = _window_metrics(results.get(benchmark_version, {}), test_start, test_end)
        for spec in specs:
            version = spec["version"]
            if version == benchmark_version:
                continue
            metrics = _window_metrics(results[version], test_start, test_end)
            alpha = round(metrics["annual_return"] - benchmark_metrics["annual_return"], 4)
            drawdown_pass = abs(metrics["max_drawdown"]) <= abs(benchmark_metrics["max_drawdown"])
            rows.append(
                {
                    "version": version,
                    "benchmark": benchmark_version,
                    "train_start": train_start.isoformat(),
                    "test_start": test_start.isoformat(),
                    "test_end": test_end.isoformat(),
                    "annual_return": metrics["annual_return"],
                    "benchmark_return": benchmark_metrics["annual_return"],
                    "alpha": alpha,
                    "max_drawdown": metrics["max_drawdown"],
                    "benchmark_drawdown": benchmark_metrics["max_drawdown"],
                    "drawdown_pass": drawdown_pass,
                    "sharpe": metrics["sharpe"],
                    "calmar": metrics["calmar"],
                }
            )

    versions = {
        version: _version_summary(version, [row for row in rows if row["version"] == version])
        for version in sorted({row["version"] for row in rows})
    }
    best = None
    if versions:
        best = max(
            versions.values(),
            key=lambda item: (item["win_rate"], item["avg_alpha"], item["drawdown_pass_rate"]),
        )["version"]
    return {
        "benchmark": benchmark_version,
        "train_years": train_years,
        "test_years": test_years,
        "windows": len({(row["test_start"], row["test_end"]) for row in rows}),
        "rows": rows,
        "versions": versions,
        "best_version": best,
    }


def _taa_kwargs(spec: dict) -> dict:
    return {
        key: value
        for key, value in spec.items()
        if key in {"score_version", "max_weight_step", "volatility_adjustment", "equity_floor_by_regime"}
    }


def _version_summary(version: str, rows: list[dict]) -> dict:
    windows = len(rows)
    wins = sum(1 for row in rows if float(row["alpha"]) > 0.0)
    drawdown_passes = sum(1 for row in rows if row.get("drawdown_pass"))
    alphas = [float(row["alpha"]) for row in rows]
    return {
        "version": version,
        "windows": windows,
        "wins": wins,
        "win_rate": round(wins / windows, 4) if windows else 0.0,
        "avg_alpha": round(sum(alphas) / windows, 4) if windows else 0.0,
        "min_alpha": round(min(alphas), 4) if alphas else 0.0,
        "drawdown_pass_rate": round(drawdown_passes / windows, 4) if windows else 0.0,
        "stable": bool(windows and wins / windows >= 0.6 and drawdown_passes / windows >= 0.6),
    }


def _window_metrics(result: dict, start: date, end: date) -> dict:
    states = [
        state for state in result.get("states", [])
        if start <= date.fromisoformat(str(state["date"])) <= end
    ]
    values = [float(state["portfolio_value"]) for state in states]
    if len(values) < 2:
        return calculate_taa_metrics(values or [1.0], [], [])
    returns = [
        current / previous - 1.0
        for previous, current in zip(values, values[1:])
        if previous > 0
    ]
    return calculate_taa_metrics(values, returns, [])


def _filter_histories(histories: dict[str, list[dict]], start: date, end: date) -> dict[str, list[dict]]:
    return {
        asset_id: [
            row for row in history
            if start <= date.fromisoformat(str(row["date"])) <= end
        ]
        for asset_id, history in histories.items()
    }


def _all_dates(histories: dict[str, list[dict]]) -> list[date]:
    return sorted(
        {
            date.fromisoformat(str(row["date"]))
            for history in histories.values()
            for row in history
        }
    )


def _empty_report(benchmark_version: str, train_years: int, test_years: int) -> dict:
    return {
        "benchmark": benchmark_version,
        "train_years": train_years,
        "test_years": test_years,
        "windows": 0,
        "rows": [],
        "versions": {},
        "best_version": None,
    }
