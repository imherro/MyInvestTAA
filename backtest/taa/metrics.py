from __future__ import annotations

from backtest.metrics import annual_return, max_drawdown, sharpe_ratio


def calculate_taa_metrics(equity_curve: list[float], returns: list[float], turnovers: list[float]) -> dict:
    max_dd = max_drawdown(equity_curve)
    ann = annual_return(equity_curve, periods_per_year=12)
    sharpe = sharpe_ratio(returns, periods_per_year=12)
    calmar = round(ann / abs(max_dd), 4) if max_dd < 0 else 0.0
    return {
        "annual_return": ann,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "calmar": calmar,
        "turnover": round(sum(turnovers), 4),
        "average_turnover": round(sum(turnovers) / len(turnovers), 4) if turnovers else 0.0,
        "ending_value": round(equity_curve[-1], 4) if equity_curve else 1.0,
    }


def drawdown_curve(equity_curve: list[float]) -> list[float]:
    peak = equity_curve[0] if equity_curve else 1.0
    values = []
    for value in equity_curve:
        peak = max(peak, value)
        values.append(round((value / peak - 1.0) * 100, 4))
    return values

