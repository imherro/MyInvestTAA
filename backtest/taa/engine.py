from __future__ import annotations

from datetime import date

from backtest.taa.metrics import calculate_taa_metrics, drawdown_curve
from backtest.taa.portfolio import PortfolioState
from backtest.taa.rebalance import build_rebalance_weights, turnover
from engine.anchor import calculate_anchor_score
from engine.asset_repository import load_assets, load_price_histories
from engine.drawdown import calculate_drawdown, calculate_drawdown_percentile, detect_drawdown_events
from engine.opportunity import _confidence_factor, _recovery_score
from engine.recovery import analyze_recovery_events
from engine.regime import detect_market_regime
from engine.risk import build_risk_budget


def run_taa_backtest(
    assets: list[dict] | None = None,
    price_history: dict[str, list[dict]] | None = None,
    rebalance_frequency: str = "monthly",
    initial_capital: float = 1.0,
    transaction_cost: float = 0.0,
    cash_return: float = 0.0,
) -> dict:
    if rebalance_frequency != "monthly":
        raise ValueError("only monthly rebalance is supported")
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if transaction_cost < 0:
        raise ValueError("transaction_cost cannot be negative")
    if cash_return <= -1:
        raise ValueError("cash_return must be greater than -1")

    if assets is None:
        assets = load_assets()
    if price_history is None:
        price_history = load_price_histories()
    dates = _all_dates(price_history)
    if len(dates) < 2:
        return _empty_result(initial_capital, transaction_cost, cash_return)

    weights = {"CASH": 100.0}
    states: list[PortfolioState] = [
        PortfolioState(
            date=dates[0].isoformat(),
            cash=initial_capital,
            positions={},
            portfolio_value=initial_capital,
            weights=weights,
            reason="initial cash position before first rebalance",
        )
    ]
    equity_curve = [initial_capital]
    returns: list[float] = []
    turnovers: list[float] = []
    value = initial_capital

    for previous_date, current_date in zip(dates, dates[1:]):
        previous_value = value
        period_return = _portfolio_return(
            weights,
            price_history,
            previous_date,
            current_date,
            cash_return,
        )
        value = value * (1.0 + period_return)

        histories_as_of = _histories_as_of(price_history, current_date)
        benchmark_history = histories_as_of.get("510300", [])
        regime = detect_market_regime(benchmark_history)
        risk_budget = build_risk_budget(regime)
        scores = _score_assets_as_of(assets, histories_as_of)
        next_weights = build_rebalance_weights(scores, risk_budget)
        period_turnover = turnover(weights, next_weights)
        turnovers.append(period_turnover)
        if transaction_cost:
            value = value * (1.0 - period_turnover * transaction_cost)
        returns.append(value / previous_value - 1.0)
        weights = next_weights

        equity_curve.append(value)
        selected_assets = [
            asset_id
            for asset_id, weight in next_weights.items()
            if asset_id != "CASH" and weight > 0
        ]
        states.append(
            PortfolioState(
                date=current_date.isoformat(),
                cash=round(value * weights.get("CASH", 0.0) / 100.0, 4),
                positions={
                    asset_id: round(value * weight / 100.0, 4)
                    for asset_id, weight in weights.items()
                    if asset_id != "CASH"
                },
                portfolio_value=round(value, 4),
                weights=weights,
                signals={
                    "scores": scores,
                    "risk_budget": risk_budget.as_dict(),
                    "turnover": period_turnover,
                    "transaction_cost": transaction_cost,
                    "cash_return": cash_return,
                },
                regime=regime.as_dict(),
                selected_assets=selected_assets,
                reason=_rebalance_reason(regime.state, selected_assets),
            )
        )

    metrics = calculate_taa_metrics(equity_curve, returns, turnovers)
    return {
        "strategy": "MyInvestTAA",
        "period": {"start": dates[0].isoformat(), "end": dates[-1].isoformat()},
        "rebalance_frequency": rebalance_frequency,
        "assumptions": {
            "transaction_cost": transaction_cost,
            "cash_return": cash_return,
        },
        "metrics": metrics,
        "equity_curve": [
            {"date": item.date, "value": item.portfolio_value}
            for item in states
        ],
        "drawdown_curve": [
            {"date": item.date, "drawdown_pct": dd}
            for item, dd in zip(states, drawdown_curve(equity_curve))
        ],
        "states": [item.as_dict() for item in states],
    }


def _score_assets_as_of(assets: list[dict], histories_as_of: dict[str, list[dict]]) -> list[dict]:
    scores: list[dict] = []
    for asset in assets:
        history = histories_as_of.get(asset["id"], [])
        if len(history) < 2:
            continue
        closes = [float(row["close"]) for row in history]
        events = detect_drawdown_events(history)
        current = calculate_drawdown(closes)
        pressure = calculate_drawdown_percentile(events, current.current_drawdown_pct)
        recovery = analyze_recovery_events(events, history, asset_id=asset["id"])
        drawdown_pressure = round(pressure["percentile"] * 100, 2)
        recovery_score = _recovery_score(recovery)
        anchor_score = calculate_anchor_score(asset)
        opportunity_score = round(
            0.4 * drawdown_pressure + 0.3 * recovery_score + 0.3 * anchor_score,
            2,
        )
        confidence_factor = _confidence_factor(recovery.sample_confidence)
        scores.append(
            {
                "id": asset["id"],
                "name": asset["name"],
                "opportunity_score": opportunity_score,
                "drawdown_pressure": drawdown_pressure,
                "recovery_score": recovery_score,
                "anchor_score": anchor_score,
                "confidence_adjusted_score": round(opportunity_score * confidence_factor, 2),
            }
        )
    return sorted(scores, key=lambda item: item["confidence_adjusted_score"], reverse=True)


def _portfolio_return(
    weights: dict[str, float],
    price_history: dict[str, list[dict]],
    previous_date: date,
    current_date: date,
    cash_return: float = 0.0,
) -> float:
    result = 0.0
    monthly_cash_return = (1.0 + cash_return) ** (1.0 / 12.0) - 1.0
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


def _all_dates(price_history: dict[str, list[dict]]) -> list[date]:
    values = {
        date.fromisoformat(str(row["date"]))
        for history in price_history.values()
        for row in history
    }
    return sorted(values)


def _histories_as_of(price_history: dict[str, list[dict]], as_of: date) -> dict[str, list[dict]]:
    return {
        asset_id: [
            row for row in history if date.fromisoformat(str(row["date"])) <= as_of
        ]
        for asset_id, history in price_history.items()
    }


def _close_on_or_before(history: list[dict], target: date) -> float | None:
    close = None
    for row in history:
        row_date = date.fromisoformat(str(row["date"]))
        if row_date <= target:
            close = float(row["close"])
        else:
            break
    return close


def _rebalance_reason(regime_state: str, selected_assets: list[str]) -> str:
    if not selected_assets:
        return f"{regime_state} regime selected cash because no positive candidates passed scoring."
    return f"{regime_state} regime selected {', '.join(selected_assets)} by confidence adjusted opportunity score."


def _empty_result(initial_capital: float, transaction_cost: float = 0.0, cash_return: float = 0.0) -> dict:
    return {
        "strategy": "MyInvestTAA",
        "period": None,
        "rebalance_frequency": "monthly",
        "assumptions": {
            "transaction_cost": transaction_cost,
            "cash_return": cash_return,
        },
        "metrics": {
            "annual_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "calmar": 0.0,
            "turnover": 0.0,
            "average_turnover": 0.0,
            "ending_value": initial_capital,
        },
        "equity_curve": [],
        "drawdown_curve": [],
        "states": [],
    }
