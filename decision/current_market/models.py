from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SourceSnapshot:
    source: str
    path: str
    sha256: str | None
    available: bool
    source_as_of: str | None
    required: bool
    temporal_role: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FreshnessCheck:
    source_as_of: str | None
    age_calendar_days: int | None
    limit_calendar_days: int | None
    stale: bool
    message: str

    def as_dict(self) -> dict:
        return asdict(self)
