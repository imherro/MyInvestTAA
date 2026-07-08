from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StressScenario:
    name: str
    label: str
    start: str
    end: str
    max_drawdown_floor: float = -20.0
    min_annual_return: float = -20.0

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "max_drawdown_floor": self.max_drawdown_floor,
            "min_annual_return": self.min_annual_return,
        }


@dataclass(frozen=True)
class StressScenarioResult:
    version: str
    scenario: str
    label: str
    start: str
    end: str
    observations: int
    annual_return: float
    max_drawdown: float
    sharpe: float
    calmar: float
    ending_value: float
    recovery_time: int | None
    pass_check: bool

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "scenario": self.scenario,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "observations": self.observations,
            "annual_return": self.annual_return,
            "max_drawdown": self.max_drawdown,
            "sharpe": self.sharpe,
            "calmar": self.calmar,
            "ending_value": self.ending_value,
            "recovery_time": self.recovery_time,
            "pass": self.pass_check,
        }
