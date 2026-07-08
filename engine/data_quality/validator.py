from __future__ import annotations

from datetime import date

from engine.data_quality.models import DataQualityReport


def validate_price_history(
    asset_id: str,
    price_history: list[dict],
    max_gap_days: int = 45,
    jump_threshold: float = 0.35,
) -> DataQualityReport:
    warnings: list[str] = []
    parsed_rows = []
    invalid_prices = 0

    for row in price_history:
        try:
            row_date = date.fromisoformat(str(row["date"]))
            close = float(row["close"])
        except (KeyError, TypeError, ValueError):
            invalid_prices += 1
            warnings.append("invalid row format")
            continue
        if close <= 0:
            invalid_prices += 1
            warnings.append(f"non-positive close on {row_date.isoformat()}")
        parsed_rows.append((row_date, close))

    dates = [item[0] for item in parsed_rows]
    duplicate_rows = len(dates) - len(set(dates))
    if duplicate_rows:
        warnings.append(f"{duplicate_rows} duplicate date rows")

    if dates != sorted(dates):
        warnings.append("dates are not sorted")

    sorted_rows = sorted(parsed_rows, key=lambda item: item[0])
    missing_days = _missing_days(sorted_rows, max_gap_days)
    if missing_days:
        warnings.append(f"{missing_days} missing calendar days beyond expected gaps")

    abnormal_jumps = _abnormal_jumps(sorted_rows, jump_threshold)
    if abnormal_jumps:
        warnings.append(f"{abnormal_jumps} abnormal price jumps")

    score = _quality_score(
        row_count=len(price_history),
        missing_days=missing_days,
        duplicate_rows=duplicate_rows,
        invalid_prices=invalid_prices,
        abnormal_jumps=abnormal_jumps,
        unsorted=dates != sorted(dates),
    )
    return DataQualityReport(
        asset_id=asset_id,
        score=score,
        row_count=len(price_history),
        missing_days=missing_days,
        duplicate_rows=duplicate_rows,
        invalid_prices=invalid_prices,
        abnormal_jumps=abnormal_jumps,
        warnings=warnings,
    )


def _missing_days(rows: list[tuple[date, float]], max_gap_days: int) -> int:
    if len(rows) < 2:
        return 0
    missing = 0
    for (previous_date, _), (current_date, _) in zip(rows, rows[1:]):
        gap = (current_date - previous_date).days
        if gap > max_gap_days:
            missing += gap - max_gap_days
    return missing


def _abnormal_jumps(rows: list[tuple[date, float]], jump_threshold: float) -> int:
    jumps = 0
    for (_, previous), (_, current) in zip(rows, rows[1:]):
        if previous <= 0:
            continue
        if abs(current / previous - 1.0) > jump_threshold:
            jumps += 1
    return jumps


def _quality_score(
    row_count: int,
    missing_days: int,
    duplicate_rows: int,
    invalid_prices: int,
    abnormal_jumps: int,
    unsorted: bool,
) -> float:
    if row_count == 0:
        return 0.0
    penalty = 0.0
    penalty += min(40.0, missing_days / 30.0 * 2.0)
    penalty += duplicate_rows * 10.0
    penalty += invalid_prices * 25.0
    penalty += abnormal_jumps * 5.0
    penalty += 10.0 if unsorted else 0.0
    return round(max(0.0, 100.0 - penalty), 2)
