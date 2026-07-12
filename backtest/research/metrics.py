from __future__ import annotations

from math import sqrt


def calculate_returns(equity_curve: list[dict]) -> list[float]:
    returns = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        if previous["value"] <= 0:
            returns.append(0.0)
        else:
            returns.append(current["value"] / previous["value"] - 1.0)
    return returns


def annual_return(equity_curve: list[dict], periods_per_year: int = 252) -> float:
    if len(equity_curve) < 2:
        return 0.0
    start = equity_curve[0]["value"]
    end = equity_curve[-1]["value"]
    if start <= 0:
        return 0.0
    years = max((len(equity_curve) - 1) / periods_per_year, 1 / periods_per_year)
    return (end / start) ** (1 / years) - 1


def max_drawdown(equity_curve: list[dict]) -> float:
    peak = None
    worst = 0.0
    for row in equity_curve:
        value = row["value"]
        peak = value if peak is None else max(peak, value)
        if peak:
            worst = min(worst, value / peak - 1.0)
    return worst


def sharpe_ratio(equity_curve: list[dict], periods_per_year: int = 252) -> float:
    returns = calculate_returns(equity_curve)
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    std = sqrt(variance)
    if std == 0:
        return 0.0
    return mean / std * sqrt(periods_per_year)


def calmar_ratio(equity_curve: list[dict], periods_per_year: int = 252) -> float:
    mdd = abs(max_drawdown(equity_curve))
    if mdd == 0:
        return 0.0
    return annual_return(equity_curve, periods_per_year=periods_per_year) / mdd


def build_metrics(equity_curve: list[dict], periods_per_year: int = 252) -> dict:
    return {
        "annual_return": round(annual_return(equity_curve, periods_per_year), 6),
        "max_drawdown": round(max_drawdown(equity_curve), 6),
        "sharpe": round(sharpe_ratio(equity_curve, periods_per_year), 6),
        "calmar": round(calmar_ratio(equity_curve, periods_per_year), 6),
    }
