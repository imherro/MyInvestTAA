from __future__ import annotations

from backtest.stress.models import StressScenario


DEFAULT_STRESS_SCENARIOS = [
    StressScenario("2018_bear", "2018 Bear", "2018-01-01", "2018-12-31"),
    StressScenario("2020_covid", "2020 Covid", "2020-01-01", "2020-04-30"),
    StressScenario("2021_growth_drawdown", "2021 Growth Drawdown", "2021-02-01", "2021-12-31"),
    StressScenario("2022_bear_market", "2022 Bear Market", "2022-01-01", "2022-12-31"),
    StressScenario("2024_rotation", "2024 Rotation", "2024-01-01", "2024-12-31"),
]
