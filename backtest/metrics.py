from __future__ import annotations

import math


def annual_return(equity_curve: list[float], periods_per_year: int = 252) -> float:
    if len(equity_curve) < 2:
        return 0.0
    total_return = equity_curve[-1] / equity_curve[0] - 1.0
    years = (len(equity_curve) - 1) / periods_per_year
    if years <= 0:
        return 0.0
    return round(((1 + total_return) ** (1 / years) - 1) * 100, 4)


def max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return round(worst * 100, 4)


def sharpe_ratio(returns: list[float], periods_per_year: int = 252) -> float:
    if len(returns) < 2:
        return 0.0
    mean_return = sum(returns) / len(returns)
    variance = sum((item - mean_return) ** 2 for item in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return round(mean_return / std * math.sqrt(periods_per_year), 4)

