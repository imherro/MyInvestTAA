from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoredAsset:
    asset_id: str
    name: str
    asset_class: str
    source: str

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "asset_class": self.asset_class,
            "source": self.source,
        }


@dataclass(frozen=True)
class StoredPrice:
    asset_id: str
    date: str
    close: float
    source: str
    adjust_type: str = "none"
    return_type: str = "price"

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "date": self.date,
            "close": self.close,
            "source": self.source,
            "adjust_type": self.adjust_type,
            "return_type": self.return_type,
        }


@dataclass(frozen=True)
class StoredSignal:
    date: str
    asset_id: str
    drawdown_score: float
    recovery_score: float
    anchor_score: float
    opportunity_score: float
    regime: str

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "asset_id": self.asset_id,
            "drawdown_score": self.drawdown_score,
            "recovery_score": self.recovery_score,
            "anchor_score": self.anchor_score,
            "opportunity_score": self.opportunity_score,
            "regime": self.regime,
        }


@dataclass(frozen=True)
class StoredBacktestResult:
    strategy: str
    period: str
    metrics: dict

    def as_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "period": self.period,
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class StoredDatasetVersion:
    dataset_id: str
    source: str
    created_at: str
    start_date: str
    end_date: str
    asset_count: int
    checksum: str

    def as_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "source": self.source,
            "created_at": self.created_at,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "asset_count": self.asset_count,
            "checksum": self.checksum,
        }


@dataclass(frozen=True)
class StoredExperiment:
    experiment_id: str
    config_hash: str
    dataset_id: str
    created_at: str
    result: dict

    def as_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "config_hash": self.config_hash,
            "dataset_id": self.dataset_id,
            "created_at": self.created_at,
            "result": self.result,
        }
