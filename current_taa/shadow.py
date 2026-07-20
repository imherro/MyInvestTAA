from __future__ import annotations

from current_taa.allocation import map_index_weights
from current_taa.model import build_metrics


BACKGROUND_BENCHMARK_ID = "510500.SH"
BACKGROUND_BENCHMARK_NAME = "南方中证500ETF"


def next_trade_date(trade_dates: list[str], value: str) -> str | None:
    return next((date for date in trade_dates if date >= value), None)


def build_shadow(
    research: dict,
    assets: list[dict],
    mappings: list[dict],
    etf_prices: dict[str, list[dict]],
    trade_dates: list[str],
    requested_start_date: str,
) -> dict:
    benchmark_rows = etf_prices.get(BACKGROUND_BENCHMARK_ID, [])
    benchmark_map = {row["date"]: float(row["close"]) for row in benchmark_rows}
    data_end = min(
        research["period"]["end"],
        max(benchmark_map) if benchmark_map else research["period"]["end"],
    )
    dates = [date for date in trade_dates if requested_start_date <= date <= data_end]
    dates = [date for date in dates if date in benchmark_map]
    if not dates:
        raise ValueError("Shadow start date is later than available qfq ETF data")
    start_date = dates[0]

    eligible_allocations = [
        row for row in research["monthly_allocations"] if row["effective_date"] <= start_date
    ]
    if not eligible_allocations:
        raise ValueError("no CURRENT_TAA allocation is available at Shadow start")
    initial = eligible_allocations[-1]
    mapped = map_index_weights(
        initial["weights"], assets, mappings, etf_prices, start_date, require_exact_date=True
    )
    current_weights = mapped["weights"]
    price_maps = {
        etf_id: {row["date"]: float(row["close"]) for row in rows}
        for etf_id, rows in etf_prices.items()
    }
    last_prices = {
        etf_id: price_maps.get(etf_id, {}).get(start_date)
        for etf_id in current_weights
        if etf_id != "CASH"
    }
    shadow_curve = [{"date": start_date, "value": 1.0}]
    benchmark_curve = [{"date": start_date, "value": 1.0}]
    rebalances = [
        {
            "signal_date": initial["signal_date"],
            "execution_date": start_date,
            "reason": "Shadow正式启用",
            "weights": current_weights,
            "cash_reasons": mapped["cash_reasons"],
        }
    ]
    future_by_date = {
        row["effective_date"]: row
        for row in research["monthly_allocations"]
        if start_date < row["effective_date"] <= data_end
    }

    previous_benchmark = benchmark_map[start_date]
    for date in dates[1:]:
        daily_return = 0.0
        for etf_id, weight in current_weights.items():
            if etf_id == "CASH":
                continue
            current = price_maps.get(etf_id, {}).get(date)
            previous = last_prices.get(etf_id)
            if current is not None and previous is not None and previous > 0:
                daily_return += float(weight) * (current / previous - 1.0)
                last_prices[etf_id] = current
        shadow_curve.append(
            {"date": date, "value": round(shadow_curve[-1]["value"] * (1.0 + daily_return), 8)}
        )
        benchmark_close = benchmark_map[date]
        benchmark_curve.append(
            {
                "date": date,
                "value": round(benchmark_curve[-1]["value"] * benchmark_close / previous_benchmark, 8),
            }
        )
        previous_benchmark = benchmark_close

        allocation = future_by_date.get(date)
        if allocation is not None:
            mapped = map_index_weights(
                allocation["weights"], assets, mappings, etf_prices, date, require_exact_date=True
            )
            current_weights = mapped["weights"]
            last_prices = {
                etf_id: price_maps.get(etf_id, {}).get(date)
                for etf_id in current_weights
                if etf_id != "CASH"
            }
            rebalances.append(
                {
                    "signal_date": allocation["signal_date"],
                    "execution_date": date,
                    "reason": "月末指数信号在下一交易日执行",
                    "weights": current_weights,
                    "cash_reasons": mapped["cash_reasons"],
                }
            )

    return {
        "model": research["model"],
        "status": "tracking",
        "requested_start_date": requested_start_date,
        "start_date": start_date,
        "end_date": shadow_curve[-1]["date"],
        "return_basis": "qfq",
        "initial_nav": 1.0,
        "equity_curve": shadow_curve,
        "metrics": build_metrics(shadow_curve),
        "background_benchmark": {
            "asset_id": BACKGROUND_BENCHMARK_ID,
            "name": BACKGROUND_BENCHMARK_NAME,
            "role": "同期市场背景基准，不是同风险正式绩效基准",
            "equity_curve": benchmark_curve,
            "metrics": build_metrics(benchmark_curve),
        },
        "rebalance_records": rebalances,
        "disclosures": [
            "Shadow为ETF前复权价格口径的可跟踪模拟，不是券商账户收益。",
            "指数与ETF存在管理费、跟踪误差、现金拖累和折溢价差异。",
            "Shadow启用历史不能替代全收益指数长期研究。",
        ],
    }
