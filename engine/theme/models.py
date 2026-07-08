from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeMapping:
    asset: str
    theme: str

    def as_dict(self) -> dict:
        return {"asset": self.asset, "theme": self.theme}


@dataclass(frozen=True)
class ThemeMomentumScore:
    theme: str
    momentum_score: float
    weighted_return: float
    members: list[str]
    windows: dict[str, float | None]

    def as_dict(self) -> dict:
        return {
            "theme": self.theme,
            "momentum_score": self.momentum_score,
            "weighted_return": self.weighted_return,
            "members": self.members,
            "windows": self.windows,
        }
