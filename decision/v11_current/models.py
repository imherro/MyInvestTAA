from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class V11ValidationResult:
    valid: bool
    errors: list[str]
    weight_sum_percent: float | None
    weight_sum_fraction: float | None
    negative_weights: list[str]
    selected_asset_mismatches: list[str]

    def as_dict(self) -> dict:
        return asdict(self)
