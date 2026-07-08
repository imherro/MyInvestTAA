from __future__ import annotations


def median_number(values: list[float | int | None]) -> float | int | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None

    middle = len(clean) // 2
    if len(clean) % 2:
        return clean[middle]
    return (clean[middle - 1] + clean[middle]) / 2


def round_optional(value: float | int | None, digits: int = 4) -> float | int | None:
    if value is None:
        return None
    return round(float(value), digits)

