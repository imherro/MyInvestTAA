from __future__ import annotations

from datetime import date

from backtest.taa import run_taa_backtest
from engine.asset_repository import load_assets, load_price_histories
from engine.performance_attribution.models import PerformanceAttributionReport


def analyze_performance_contribution(
    backtest_result: dict | None = None,
    price_history: dict[str, list[dict]] | None = None,
) -> dict:
    if price_history is None:
        price_history = load_price_histories()
    if backtest_result is None:
        backtest_result = run_taa_backtest(assets=load_assets(), price_history=price_history)

    states = backtest_result.get("states", [])
    asset_contribution: dict[str, float] = {}
    periods: list[dict] = []

    for previous, current in zip(states, states[1:]):
        previous_date = date.fromisoformat(previous["date"])
        current_date = date.fromisoformat(current["date"])
        weights = previous.get("weights") or {}
        contributions: dict[str, float] = {}
        for asset_id, weight in weights.items():
            if asset_id == "CASH":
                continue
            asset_return = _asset_return(price_history.get(asset_id, []), previous_date, current_date)
            contribution = round((float(weight) / 100.0) * asset_return * 100.0, 4)
            if contribution:
                contributions[asset_id] = contribution
                asset_contribution[asset_id] = round(
                    asset_contribution.get(asset_id, 0.0) + contribution,
                    4,
                )
        periods.append(
            {
                "period": f"{previous['date']}:{current['date']}",
                "date": current["date"],
                "contribution": contributions,
            }
        )

    top = [
        {"asset_id": asset_id, "contribution": contribution}
        for asset_id, contribution in sorted(
            asset_contribution.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
    report = PerformanceAttributionReport(
        strategy=backtest_result.get("strategy", "MyInvestTAA"),
        asset_contribution=asset_contribution,
        periods=periods,
        top_contributors=top[:5],
    )
    return report.as_dict()


def _asset_return(history: list[dict], previous_date: date, current_date: date) -> float:
    previous_close = _close_on_or_before(history, previous_date)
    current_close = _close_on_or_before(history, current_date)
    if previous_close is None or current_close is None or previous_close <= 0:
        return 0.0
    return current_close / previous_close - 1.0


def _close_on_or_before(history: list[dict], target: date) -> float | None:
    close = None
    for row in history:
        row_date = date.fromisoformat(str(row["date"]))
        if row_date <= target:
            close = float(row["close"])
        else:
            break
    return close
