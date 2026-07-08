from __future__ import annotations

from datetime import date
from statistics import median

from backtest.benchmark import compare_strategies
from backtest.metrics import max_drawdown


DEFAULT_WINDOWS = {
    "1Y": 1,
    "3Y": 3,
    "5Y": 5,
}


def rolling_analysis(
    comparison: dict | None = None,
    windows: dict[str, int] | None = None,
    primary_benchmark: str = "HS300_BUY_HOLD",
) -> dict:
    if comparison is None:
        comparison = compare_strategies()
    if windows is None:
        windows = DEFAULT_WINDOWS

    taa_curve = _parse_curve(comparison["equity_curves"].get("MyInvestTAA", []))
    benchmark_curves = {
        strategy_id: _parse_curve(curve)
        for strategy_id, curve in comparison["equity_curves"].items()
        if strategy_id != "MyInvestTAA"
    }

    window_results = []
    for label, years in windows.items():
        benchmark_results = {
            strategy_id: _rolling_against_benchmark(taa_curve, curve, years)
            for strategy_id, curve in benchmark_curves.items()
        }
        primary = benchmark_results.get(primary_benchmark) or _empty_window(years)
        window_results.append(
            {
                "rolling_period": label,
                "years": years,
                "rolling_win_rate": primary["win_rate"],
                "avg_alpha": primary["avg_alpha"],
                "benchmarks": benchmark_results,
            }
        )

    primary_3y = next(
        (item for item in window_results if item["rolling_period"] == "3Y"),
        window_results[0] if window_results else {"rolling_win_rate": 0.0, "avg_alpha": 0.0},
    )
    return {
        "strategy": "MyInvestTAA",
        "primary_benchmark": primary_benchmark,
        "rolling_win_rate": primary_3y["rolling_win_rate"],
        "avg_alpha": primary_3y["avg_alpha"],
        "windows": window_results,
    }


def _rolling_against_benchmark(
    taa_curve: list[tuple[date, float]],
    benchmark_curve: list[tuple[date, float]],
    years: int,
) -> dict:
    if len(taa_curve) < 2 or len(benchmark_curve) < 2:
        return _empty_window(years)

    alphas: list[float] = []
    drawdown_improvements: list[float] = []
    for end_date, taa_end in taa_curve:
        start_date = _shift_year(end_date, years)
        taa_start = _value_on_or_before(taa_curve, start_date)
        benchmark_start = _value_on_or_before(benchmark_curve, start_date)
        benchmark_end = _value_on_or_before(benchmark_curve, end_date)
        if taa_start is None or benchmark_start is None or benchmark_end is None:
            continue
        if start_date < taa_curve[0][0] or start_date < benchmark_curve[0][0]:
            continue

        taa_return = _annualized_return(taa_start, taa_end, years)
        benchmark_return = _annualized_return(benchmark_start, benchmark_end, years)
        alphas.append(round(taa_return - benchmark_return, 4))

        taa_window = _window_values(taa_curve, start_date, end_date, taa_start, taa_end)
        benchmark_window = _window_values(benchmark_curve, start_date, end_date, benchmark_start, benchmark_end)
        drawdown_improvements.append(
            round(abs(max_drawdown(benchmark_window)) - abs(max_drawdown(taa_window)), 4)
        )

    if not alphas:
        return _empty_window(years)

    return {
        "years": years,
        "observations": len(alphas),
        "win_rate": round(sum(1 for value in alphas if value > 0) / len(alphas), 4),
        "avg_alpha": round(sum(alphas) / len(alphas), 4),
        "median_alpha": round(median(alphas), 4),
        "min_alpha": round(min(alphas), 4),
        "max_alpha": round(max(alphas), 4),
        "positive_drawdown_improvement_rate": round(
            sum(1 for value in drawdown_improvements if value > 0) / len(drawdown_improvements),
            4,
        ),
        "avg_drawdown_improvement": round(sum(drawdown_improvements) / len(drawdown_improvements), 4),
    }


def _empty_window(years: int) -> dict:
    return {
        "years": years,
        "observations": 0,
        "win_rate": 0.0,
        "avg_alpha": 0.0,
        "median_alpha": 0.0,
        "min_alpha": 0.0,
        "max_alpha": 0.0,
        "positive_drawdown_improvement_rate": 0.0,
        "avg_drawdown_improvement": 0.0,
    }


def _parse_curve(curve: list[dict]) -> list[tuple[date, float]]:
    return [
        (date.fromisoformat(str(point["date"])), float(point["value"]))
        for point in curve
    ]


def _shift_year(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _value_on_or_before(curve: list[tuple[date, float]], target: date) -> float | None:
    value = None
    for item_date, item_value in curve:
        if item_date <= target:
            value = item_value
        else:
            break
    return value


def _window_values(
    curve: list[tuple[date, float]],
    start_date: date,
    end_date: date,
    start_value: float,
    end_value: float,
) -> list[float]:
    values = [start_value]
    values.extend(item_value for item_date, item_value in curve if start_date < item_date < end_date)
    values.append(end_value)
    return values


def _annualized_return(start_value: float, end_value: float, years: int) -> float:
    if start_value <= 0 or years <= 0:
        return 0.0
    return ((end_value / start_value) ** (1.0 / years) - 1.0) * 100.0
