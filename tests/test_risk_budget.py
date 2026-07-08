from engine.regime.models import MarketRegime
from engine.risk import build_risk_budget


def test_risk_budget_bull_allows_high_equity():
    budget = build_risk_budget(MarketRegime("bull", 0.8, 90.0, "bull"))

    assert budget.equity_limit == 90.0
    assert budget.min_cash == 10.0
    assert budget.max_single_asset == 45.0


def test_risk_budget_bear_caps_equity():
    budget = build_risk_budget(MarketRegime("bear", 0.8, 40.0, "bear"))

    assert budget.equity_limit == 40.0
    assert budget.min_cash == 60.0
    assert budget.max_single_asset == 25.0


def test_risk_budget_recovery_uses_medium_cap():
    budget = build_risk_budget(MarketRegime("bear_recovery", 0.7, 70.0, "recovery"))

    assert budget.equity_limit == 70.0
    assert budget.min_cash == 30.0
    assert budget.max_single_asset == 35.0


def test_risk_budget_neutral_description_mentions_cap():
    budget = build_risk_budget(MarketRegime("neutral", 0.6, 70.0, "neutral"))

    assert "70%" in budget.description
