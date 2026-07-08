from __future__ import annotations

from engine.regime.models import MarketRegime
from engine.risk.models import RiskBudget


def build_risk_budget(regime: MarketRegime) -> RiskBudget:
    equity_limit = regime.equity_limit
    min_cash = round(100.0 - equity_limit, 2)
    max_single_asset = _max_single_asset(regime.state)
    return RiskBudget(
        regime_state=regime.state,
        equity_limit=equity_limit,
        min_cash=min_cash,
        max_single_asset=max_single_asset,
        description=f"{regime.state} regime caps equity exposure at {equity_limit:.0f}%.",
    )


def _max_single_asset(state: str) -> float:
    if state == "bull":
        return 45.0
    if state in {"bull_caution", "neutral", "bear_recovery"}:
        return 35.0
    if state == "bear":
        return 25.0
    return 35.0

