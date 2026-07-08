from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkStrategy:
    strategy_id: str
    name: str
    weights: dict[str, float]
    description: str

    def as_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "weights": self.weights,
            "description": self.description,
        }


@dataclass(frozen=True)
class BenchmarkResult:
    strategy: BenchmarkStrategy
    period: dict | None
    metrics: dict
    equity_curve: list[dict]
    drawdown_curve: list[dict]

    def as_dict(self) -> dict:
        return {
            "strategy_id": self.strategy.strategy_id,
            "name": self.strategy.name,
            "description": self.strategy.description,
            "weights": self.strategy.weights,
            "period": self.period,
            "metrics": self.metrics,
            "equity_curve": self.equity_curve,
            "drawdown_curve": self.drawdown_curve,
        }


def normalize_benchmark_weights(weights: dict[str, float]) -> dict[str, float]:
    if not weights:
        return {"CASH": 100.0}
    if any(weight < 0 for weight in weights.values()):
        raise ValueError("benchmark weights cannot be negative")

    total = sum(weights.values())
    if total <= 0:
        return {"CASH": 100.0}

    normalized = {
        asset_id: round(weight / total * 100.0, 4)
        for asset_id, weight in weights.items()
        if weight > 0
    }
    drift = round(100.0 - sum(normalized.values()), 4)
    if drift:
        key = "CASH" if "CASH" in normalized else next(iter(normalized))
        normalized[key] = round(normalized[key] + drift, 4)
    return normalized
