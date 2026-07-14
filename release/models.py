from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class ReleaseBuildConfig:
    market_data_as_of: str
    decision_date: str
    generated_at: str
    provider: str
    output_dir: str
    commit_sha: str

    def validate(self) -> None:
        date.fromisoformat(self.market_data_as_of)
        date.fromisoformat(self.decision_date)
        generated = datetime.fromisoformat(self.generated_at.replace("Z", "+00:00"))
        if generated.tzinfo is None:
            raise ValueError("generated_at must include a timezone")
        if self.provider != "local":
            raise ValueError("release provider must be local")
        if date.fromisoformat(self.market_data_as_of) > date.fromisoformat(self.decision_date):
            raise ValueError("market_data_as_of must not be after decision_date")
        if not self.commit_sha or len(self.commit_sha) != 40:
            raise ValueError("commit_sha must be a full Git SHA")

    def as_dict(self) -> dict:
        return {
            "market_data_as_of": self.market_data_as_of,
            "decision_date": self.decision_date,
            "generated_at": self.generated_at,
            "provider": self.provider,
            "output_dir": self.output_dir,
            "commit_sha": self.commit_sha,
        }


@dataclass(frozen=True)
class SourceDefinition:
    path: str
    role: str
    classification: str
    source_as_of: str | None = None


@dataclass(frozen=True)
class ArtifactDefinition:
    path: str
    role: str
    classification: str
    dependencies: tuple[str, ...]
