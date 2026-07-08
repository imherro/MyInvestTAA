from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DataQualityReport:
    asset_id: str
    score: float
    row_count: int
    missing_days: int
    duplicate_rows: int
    invalid_prices: int
    abnormal_jumps: int
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "score": self.score,
            "row_count": self.row_count,
            "missing_days": self.missing_days,
            "duplicate_rows": self.duplicate_rows,
            "invalid_prices": self.invalid_prices,
            "abnormal_jumps": self.abnormal_jumps,
            "warnings": self.warnings,
        }
