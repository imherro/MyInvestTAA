from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryEventAnalysis:
    bottom_date: str
    drawdown_pct: float
    recovered: bool
    recovery_days: int | None
    forward_return_1y_pct: float | None
    forward_return_2y_pct: float | None
    forward_return_3y_pct: float | None

    def as_dict(self) -> dict:
        return {
            "bottom_date": self.bottom_date,
            "drawdown_pct": self.drawdown_pct,
            "recovered": self.recovered,
            "recovery_days": self.recovery_days,
            "forward_return_1y_pct": self.forward_return_1y_pct,
            "forward_return_2y_pct": self.forward_return_2y_pct,
            "forward_return_3y_pct": self.forward_return_3y_pct,
        }


@dataclass(frozen=True)
class RecoverySummary:
    asset_id: str | None
    event_count: int
    recovered_events: int
    recovery_probability: float
    sample_confidence: str
    median_recovery_days: int | None
    median_forward_return_1y_pct: float | None
    median_forward_return_2y_pct: float | None
    median_forward_return_3y_pct: float | None
    events: list[RecoveryEventAnalysis]

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "event_count": self.event_count,
            "recovered_events": self.recovered_events,
            "recovery_probability": self.recovery_probability,
            "sample_confidence": self.sample_confidence,
            "median_recovery_days": self.median_recovery_days,
            "median_forward_return_1y_pct": self.median_forward_return_1y_pct,
            "median_forward_return_2y_pct": self.median_forward_return_2y_pct,
            "median_forward_return_3y_pct": self.median_forward_return_3y_pct,
            "events": [event.as_dict() for event in self.events],
        }
