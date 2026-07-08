from __future__ import annotations

from backtest.taa import run_taa_backtest
from engine.attribution.models import AttributionReport


FACTOR_KEYS = ("drawdown", "recovery", "anchor", "regime", "allocation")


def analyze_attribution(backtest_result: dict | None = None) -> dict:
    if backtest_result is None:
        backtest_result = run_taa_backtest()

    raw = {key: 0.0 for key in FACTOR_KEYS}
    observations = 0
    for state in backtest_result.get("states", []):
        signals = state.get("signals") or {}
        score_map = {
            item["id"]: item
            for item in signals.get("scores", [])
            if "id" in item
        }
        weights = state.get("weights") or {}
        selected_assets = state.get("selected_assets") or []
        if not selected_assets:
            continue

        observations += 1
        for asset_id in selected_assets:
            score = score_map.get(asset_id)
            if not score:
                continue
            weight = float(weights.get(asset_id, 0.0)) / 100.0
            raw["drawdown"] += weight * float(score.get("drawdown_pressure", 0.0)) * 0.4
            raw["recovery"] += weight * float(score.get("recovery_score", 0.0)) * 0.3
            raw["anchor"] += weight * float(score.get("anchor_score", 0.0)) * 0.3

        risk_budget = signals.get("risk_budget") or {}
        equity_limit = float(risk_budget.get("equity_limit", 100.0))
        raw["regime"] += max(0.0, 100.0 - equity_limit) / 100.0 * 25.0
        raw["allocation"] += float(signals.get("turnover", 0.0)) * 100.0

    contribution = _normalize_contribution(raw)
    dominant_factor = max(contribution, key=contribution.get) if contribution else "none"
    report = AttributionReport(
        strategy=backtest_result.get("strategy", "MyInvestTAA"),
        contribution=contribution,
        observations=observations,
        dominant_factor=dominant_factor,
        notes=[
            "Score attribution uses recorded rebalance signals, not causal performance decomposition.",
            "Contribution values sum to 100 when signal observations are available.",
        ],
    )
    return report.as_dict()


def _normalize_contribution(raw: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in raw.values())
    if total <= 0:
        return {key: 0.0 for key in FACTOR_KEYS}
    normalized = {
        key: round(max(0.0, value) / total * 100.0, 2)
        for key, value in raw.items()
    }
    drift = round(100.0 - sum(normalized.values()), 2)
    if drift:
        key = max(normalized, key=normalized.get)
        normalized[key] = round(normalized[key] + drift, 2)
    return normalized
