from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetAnchorProfile:
    asset_id: str
    cashflow_score: float
    profitability_score: float
    balance_sheet_score: float
    valuation_anchor_score: float
    lifecycle_score: float
    anchor_score: float
    confidence: str

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "cashflow_score": self.cashflow_score,
            "profitability_score": self.profitability_score,
            "balance_sheet_score": self.balance_sheet_score,
            "valuation_anchor_score": self.valuation_anchor_score,
            "lifecycle_score": self.lifecycle_score,
            "anchor_score": self.anchor_score,
            "confidence": self.confidence,
        }

