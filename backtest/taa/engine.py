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
from engine.selection import calculate_relative_strength


def run_taa_backtest(
    assets: list[dict] | None = None,
    price_history: dict[str, list[dict]] | None = None,
    rebalance_frequency: str = "monthly",
    initial_capital: float = 1.0,
    transaction_cost: float = 0.0,
    cash_return: float = 0.0,
    slippage: float = 0.0,
    expense_ratio: float = 0.0,
    score_version: str = "v1",
    max_weight_step: float | None = None,
    volatility_adjustment: bool = False,
    equity_floor_by_regime: dict[str, float] | None = None,
) -> dict:
    if rebalance_frequency != "monthly":
        raise ValueError("only monthly rebalance is supported")
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if transaction_cost < 0:
        raise ValueError("transaction_cost cannot be negative")
    if slippage < 0:
        raise ValueError("slippage cannot be negative")
    if expense_ratio < 0:
        raise ValueError("expense_ratio cannot be negative")
    if cash_return <= -1:
        raise ValueError("cash_return must be greater than -1")
    if score_version not in {"v1", "v4", "v5"}:
        raise ValueError("score_version must be v1, v4, or v5")
    if max_weight_step is not None and max_weight_step <= 0:
        raise ValueError("max_weight_step must be positive")
    if equity_floor_by_regime:
        for state, floor in equity_floor_by_regime.items():
            if floor < 0 or floor > 100:
                raise ValueError(f"equity floor must be between 0 and 100: {state}")

    if assets is None:
        assets = load_assets()
    if price_history is None:
        price_history = load_price_histories()
    dates = _all_dates(price_history)
    if len(dates) < 2:
        return _empty_result(
            initial_capital,
            transaction_cost,
            cash_return,
            slippage,
            expense_ratio,
            score_version,
            max_weight_step,
            volatility_adjustment,
            equity_floor_by_regime,
        )

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
        if expense_ratio:
            value = value * (1.0 - expense_ratio / 12.0)

        histories_as_of = _histories_as_of(price_history, current_date)
        benchmark_history = histories_as_of.get("510300", [])
        regime = detect_market_regime(benchmark_history)
        risk_budget = build_risk_budget(regime)
        assets_as_of = _assets_available_as_of(assets, current_date)
        scores = _score_assets_as_of(assets_as_of, histories_as_of, score_version=score_version)
        scoring_weights = _apply_volatility_adjustment(scores) if volatility_adjustment else scores
        target_weights = build_rebalance_weights(scoring_weights, risk_budget)
        next_weights = (
            _smooth_weight_transition(weights, target_weights, max_weight_step)
            if max_weight_step is not None
            else target_weights
        )
        if equity_floor_by_regime:
            floor = equity_floor_by_regime.get(regime.state)
            if floor is not None:
                next_weights = _apply_equity_floor(next_weights, scoring_weights, floor)
        period_turnover = turnover(weights, next_weights)
        turnovers.append(period_turnover)
        friction = transaction_cost + slippage
        if friction:
            value = value * (1.0 - period_turnover * friction)
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
                    "slippage": slippage,
                    "expense_ratio": expense_ratio,
                    "score_version": score_version,
                    "max_weight_step": max_weight_step,
                    "volatility_adjustment": volatility_adjustment,
                    "equity_floor_by_regime": equity_floor_by_regime or {},
                    "target_weights": target_weights,
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
            "slippage": slippage,
            "expense_ratio": expense_ratio,
            "score_version": score_version,
            "max_weight_step": max_weight_step,
            "volatility_adjustment": volatility_adjustment,
            "equity_floor_by_regime": equity_floor_by_regime or {},
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


def _score_assets_as_of(
    assets: list[dict],
    histories_as_of: dict[str, list[dict]],
    score_version: str = "v1",
) -> list[dict]:
    scores: list[dict] = []
    benchmark_history = histories_as_of.get("510300", [])
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
        trend_score = _trend_score(history)
        volatility = _volatility(history)
        relative_strength = calculate_relative_strength(asset["id"], history, benchmark_history)
        if score_version == "v4":
            opportunity_score = round(
                0.3 * drawdown_pressure
                + 0.25 * recovery_score
                + 0.25 * anchor_score
                + 0.2 * trend_score,
                2,
            )
        elif score_version == "v5":
            opportunity_score = round(
                0.25 * drawdown_pressure
                + 0.20 * recovery_score
                + 0.20 * anchor_score
                + 0.20 * trend_score
                + 0.15 * relative_strength.strength_score,
                2,
            )
        else:
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
                "trend_score": trend_score,
                "relative_strength_score": relative_strength.strength_score,
                "relative_strength": relative_strength.as_dict(),
                "volatility": volatility,
                "confidence_adjusted_score": round(opportunity_score * confidence_factor, 2),
            }
        )
    return sorted(scores, key=lambda item: item["confidence_adjusted_score"], reverse=True)


def _trend_score(history: list[dict]) -> float:
    closes = [float(row["close"]) for row in history]
    if len(closes) < 3:
        return 0.0
    current = closes[-1]
    short_ma = sum(closes[-3:]) / min(3, len(closes))
    long_sample = closes[-6:] if len(closes) >= 6 else closes
    long_ma = sum(long_sample) / len(long_sample)
    lookback = closes[-4] if len(closes) >= 4 else closes[0]
    momentum = current / lookback - 1.0 if lookback > 0 else 0.0
    ma_component = 50.0 if current >= short_ma >= long_ma else 25.0 if current >= long_ma else 0.0
    momentum_component = max(0.0, min(50.0, 25.0 + momentum * 250.0))
    return round(ma_component + momentum_component, 2)


def _volatility(history: list[dict]) -> float:
    closes = [float(row["close"]) for row in history]
    if len(closes) < 3:
        return 0.0
    returns = [
        current / previous - 1.0
        for previous, current in zip(closes, closes[1:])
        if previous > 0
    ]
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / len(returns)
    return round(variance ** 0.5, 6)


def _apply_volatility_adjustment(scores: list[dict]) -> list[dict]:
    adjusted = []
    for item in scores:
        volatility = max(float(item.get("volatility", 0.0)), 0.02)
        score = dict(item)
        score["confidence_adjusted_score"] = round(
            float(item.get("confidence_adjusted_score", 0.0)) / volatility,
            2,
        )
        adjusted.append(score)
    return sorted(adjusted, key=lambda item: item["confidence_adjusted_score"], reverse=True)


def _smooth_weight_transition(
    previous: dict[str, float],
    target: dict[str, float],
    max_step: float,
) -> dict[str, float]:
    asset_ids = set(previous) | set(target)
    smoothed: dict[str, float] = {}
    for asset_id in asset_ids:
        old = previous.get(asset_id, 0.0)
        desired = target.get(asset_id, 0.0)
        change = desired - old
        if change > max_step:
            value = old + max_step
        elif change < -max_step:
            value = old - max_step
        else:
            value = desired
        if value > 0:
            smoothed[asset_id] = round(value, 4)
    total = sum(smoothed.values())
    if total <= 0:
        return {"CASH": 100.0}
    drift = round(100.0 - total, 4)
    smoothed["CASH"] = round(smoothed.get("CASH", 0.0) + drift, 4)
    return {asset_id: weight for asset_id, weight in smoothed.items() if weight > 0}


def _apply_equity_floor(
    weights: dict[str, float],
    scores: list[dict],
    floor: float,
) -> dict[str, float]:
    invested = sum(weight for asset_id, weight in weights.items() if asset_id != "CASH")
    if invested >= floor:
        return weights
    candidates = [item["id"] for item in scores if item["id"] != "CASH"]
    if not candidates:
        return weights
    deficit = min(floor - invested, weights.get("CASH", 0.0))
    if deficit <= 0:
        return weights
    adjusted = dict(weights)
    per_asset = deficit / min(len(candidates), 3)
    for asset_id in candidates[:3]:
        adjusted[asset_id] = round(adjusted.get(asset_id, 0.0) + per_asset, 4)
    adjusted["CASH"] = round(adjusted.get("CASH", 0.0) - deficit, 4)
    drift = round(100.0 - sum(adjusted.values()), 4)
    adjusted["CASH"] = round(adjusted.get("CASH", 0.0) + drift, 4)
    return {asset_id: weight for asset_id, weight in adjusted.items() if weight > 0}


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


def _assets_available_as_of(assets: list[dict], current_date: date) -> list[dict]:
    available = []
    for asset in assets:
        start = asset.get("start_date")
        end = asset.get("end_date")
        if start and current_date < date.fromisoformat(str(start)):
            continue
        if end and current_date > date.fromisoformat(str(end)):
            continue
        available.append(asset)
    return available


def _rebalance_reason(regime_state: str, selected_assets: list[str]) -> str:
    if not selected_assets:
        return f"{regime_state} regime selected cash because no positive candidates passed scoring."
    return f"{regime_state} regime selected {', '.join(selected_assets)} by confidence adjusted opportunity score."


def _empty_result(
    initial_capital: float,
    transaction_cost: float = 0.0,
    cash_return: float = 0.0,
    slippage: float = 0.0,
    expense_ratio: float = 0.0,
    score_version: str = "v1",
    max_weight_step: float | None = None,
    volatility_adjustment: bool = False,
    equity_floor_by_regime: dict[str, float] | None = None,
) -> dict:
    return {
        "strategy": "MyInvestTAA",
        "period": None,
        "rebalance_frequency": "monthly",
        "assumptions": {
            "transaction_cost": transaction_cost,
            "cash_return": cash_return,
            "slippage": slippage,
            "expense_ratio": expense_ratio,
            "score_version": score_version,
            "max_weight_step": max_weight_step,
            "volatility_adjustment": volatility_adjustment,
            "equity_floor_by_regime": equity_floor_by_regime or {},
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
