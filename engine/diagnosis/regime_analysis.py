from __future__ import annotations


def analyze_regime_effects(backtest_result: dict) -> dict:
    states = backtest_result.get("states", [])
    grouped: dict[str, dict] = {}
    for previous, current in zip(states, states[1:]):
        previous_value = float(previous.get("portfolio_value", 0.0))
        current_value = float(current.get("portfolio_value", 0.0))
        if previous_value <= 0:
            continue
        regime = (
            (current.get("regime") or {}).get("state")
            or (previous.get("regime") or {}).get("state")
            or "unknown"
        )
        period_return = (current_value / previous_value - 1.0) * 100.0
        equity_exposure = 100.0 - float(current.get("weights", {}).get("CASH", 0.0))
        bucket = grouped.setdefault(
            regime,
            {
                "state": regime,
                "periods": 0,
                "total_return": 0.0,
                "total_exposure": 0.0,
                "allocation_effect": 0.0,
            },
        )
        bucket["periods"] += 1
        bucket["total_return"] += period_return
        bucket["total_exposure"] += equity_exposure
        bucket["allocation_effect"] += period_return * (equity_exposure / 100.0 - 0.6)

    rows = []
    for item in grouped.values():
        periods = item["periods"]
        rows.append(
            {
                "state": item["state"],
                "periods": periods,
                "avg_return": round(item["total_return"] / periods, 4),
                "avg_equity_exposure": round(item["total_exposure"] / periods, 2),
                "allocation_effect": round(item["allocation_effect"], 4),
            }
        )
    return {
        "strategy": backtest_result.get("strategy", "MyInvestTAA"),
        "regimes": sorted(rows, key=lambda item: item["allocation_effect"]),
        "worst_regime": min(rows, key=lambda item: item["allocation_effect"])["state"] if rows else None,
    }
