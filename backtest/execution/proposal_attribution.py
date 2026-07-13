from __future__ import annotations

from backtest.execution.counterfactual import run_mapping_counterfactual
from backtest.execution.drawdown_attribution import drawdown_window


def build_proposal_attribution(research, mappings, proposals, prices, assets, provider):
    rows = []
    for proposal in proposals:
        baseline, counter, common, impact = run_mapping_counterfactual(
            research, mappings, [proposal], prices, assets, data_provider=provider
        )
        baseline_window = drawdown_window(baseline)
        proposal_window = drawdown_window(counter)
        exact = build_exact_drawdown_attribution(counter, prices, proposal_window)
        rows.append(
            {
                "research_asset_id": proposal["research_asset_id"],
                "proposed_proxy": proposal["proposed_primary_execution_proxy"],
                "common_comparison_period": common,
                "marginal_impact": impact,
                "drawdown_attribution": {
                    "baseline": baseline_window,
                    "proposal": proposal_window,
                    "exact_reconciliation": exact,
                    "etf_return_contributions": exact["linked_etf_contributions"],
                    "proposal_marginal_loss_contribution": round(
                        impact["max_drawdown_delta"], 6
                    ),
                },
            }
        )
    baseline, full, common, impact = run_mapping_counterfactual(
        research, mappings, proposals, prices, assets, data_provider=provider
    )
    full_window = drawdown_window(full)
    exact = build_exact_drawdown_attribution(full, prices, full_window)
    return {
        "available": True,
        "proposal_attributions": rows,
        "full_overlay": {
            "common_comparison_period": common,
            "impact": impact,
            "baseline_drawdown": drawdown_window(baseline),
            "full_overlay_drawdown": full_window,
            "exact_reconciliation": exact,
            "etf_return_contributions": exact["linked_etf_contributions"],
            "concentration_or_market_exposure": (
                "increased_mapped_market_exposure"
                if impact["max_drawdown_delta"] < 0
                else "no_additional_drawdown"
            ),
        },
    }


def build_exact_drawdown_attribution(report, prices, window=None):
    """Link daily arithmetic contributions onto the execution equity curve."""
    window = window or drawdown_window(report)
    peak_date = window.get("peak_date")
    trough_date = window.get("trough_date")
    curve = [
        row
        for row in report.get("equity_curve", [])
        if peak_date and trough_date and peak_date <= row["date"] <= trough_date
    ]
    if len(curve) < 2:
        return _empty_reconciliation()

    price_maps = {
        asset_id: {row.date: float(row.close) for row in rows}
        for asset_id, rows in prices.items()
    }
    allocations = report.get("monthly_allocations", [])
    current = {"CASH": 1.0}
    allocation_index = 0
    linked = {}
    linked_residual = 0.0
    wealth = 1.0

    for left_row, right_row in zip(curve, curve[1:]):
        left = left_row["date"]
        right = right_row["date"]
        while (
            allocation_index < len(allocations)
            and allocations[allocation_index]["date"] <= left
        ):
            current = allocations[allocation_index]["weights"]
            allocation_index += 1

        daily_contributions = {}
        for asset_id, weight in current.items():
            if asset_id == "CASH":
                continue
            values = price_maps.get(asset_id, {})
            if left not in values or right not in values or values[left] <= 0:
                continue
            daily_contributions[asset_id] = float(weight) * (
                values[right] / values[left] - 1
            )

        portfolio_daily_return = (
            float(right_row["value"]) / float(left_row["value"]) - 1
        )
        arithmetic_total = sum(daily_contributions.values())
        for asset_id, contribution in daily_contributions.items():
            linked[asset_id] = linked.get(asset_id, 0.0) + wealth * contribution
        linked_residual += wealth * (portfolio_daily_return - arithmetic_total)
        wealth *= 1 + portfolio_daily_return

    portfolio_drawdown = float(curve[-1]["value"]) / float(curve[0]["value"]) - 1
    linked = {key: round(value, 12) for key, value in sorted(linked.items())}
    residual = round(linked_residual, 12)
    reconciled = round(sum(linked.values()) + residual, 12)
    error = round(abs(reconciled - portfolio_drawdown), 12)
    return {
        "portfolio_drawdown": round(portfolio_drawdown, 12),
        "linked_etf_contributions": linked,
        "residual": residual,
        "reconciled_total": reconciled,
        "reconciliation_error": error,
        "method": "geometric_linked_daily_contribution",
        "approximate": error > 0.000001,
        "date_alignment": "execution_equity_curve",
        "start_date": curve[0]["date"],
        "end_date": curve[-1]["date"],
        "observation_count": len(curve),
    }


def _empty_reconciliation():
    return {
        "portfolio_drawdown": 0.0,
        "linked_etf_contributions": {},
        "residual": 0.0,
        "reconciled_total": 0.0,
        "reconciliation_error": 0.0,
        "method": "geometric_linked_daily_contribution",
        "approximate": False,
        "date_alignment": "execution_equity_curve",
        "start_date": None,
        "end_date": None,
        "observation_count": 0,
    }
