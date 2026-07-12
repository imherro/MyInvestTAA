from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchBacktestConfig:
    strategy: str = "RESEARCH_TAA_MVP"
    top_n: int = 5
    lookback_6m: int = 126
    lookback_12m: int = 252
    momentum_6m_weight: float = 0.4
    momentum_12m_weight: float = 0.3
    drawdown_resilience_weight: float = 0.3
    single_asset_max: float = 0.25
    theme_sleeve_max: float = 0.20
    single_theme_max: float = 0.10
    min_assets: int = 5


@dataclass(frozen=True)
class ResearchPrice:
    asset_id: str
    date: str
    close: float
    return_basis: str

    @classmethod
    def from_mapping(cls, asset_id: str, row: dict) -> "ResearchPrice":
        return cls(
            asset_id=asset_id,
            date=str(row["date"]),
            close=float(row["close"]),
            return_basis=str(row.get("return_basis") or "unknown"),
        )

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "close": self.close,
            "return_basis": self.return_basis,
        }
