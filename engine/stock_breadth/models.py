from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StockThemeMapping:
    stock: str
    theme: str

    def as_dict(self) -> dict:
        return {"stock": self.stock, "theme": self.theme}


@dataclass(frozen=True)
class StockBreadthScore:
    theme: str
    breadth_score: float
    advancers: int
    total: int
    expected: int
    advancer_ratio: float
    above_ma_ratio: float
    new_high_ratio: float
    coverage_ratio: float
    members: list[str]
    missing_members: list[str]
    source: str = "stock_daily"

    def as_dict(self) -> dict:
        return {
            "theme": self.theme,
            "breadth_score": self.breadth_score,
            "advancers": self.advancers,
            "total": self.total,
            "expected": self.expected,
            "advancer_ratio": self.advancer_ratio,
            "above_ma_ratio": self.above_ma_ratio,
            "new_high_ratio": self.new_high_ratio,
            "coverage_ratio": self.coverage_ratio,
            "members": self.members,
            "missing_members": self.missing_members,
            "source": self.source,
        }
