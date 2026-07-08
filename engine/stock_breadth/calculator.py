from __future__ import annotations

from engine.stock_breadth.models import StockBreadthScore
from engine.stock_breadth.theme_mapping import DEFAULT_THEME_STOCK_MAPPING, stocks_for_theme, theme_for_stock


def calculate_stock_breadth(
    theme: str,
    stock_histories: dict[str, list[dict]],
    stock_ids: list[str] | None = None,
    ma_window: int = 20,
    high_window: int = 60,
    source: str = "stock_daily",
) -> StockBreadthScore:
    expected_members = stock_ids if stock_ids is not None else stocks_for_theme(theme)
    if stock_ids is None and not expected_members and theme == "unclassified":
        expected_members = sorted(stock_histories)

    advancers = 0
    above_ma = 0
    new_highs = 0
    total = 0
    observed_members: list[str] = []
    missing_members: list[str] = []

    for stock_id in expected_members:
        rows = _sorted_rows(stock_histories.get(stock_id, []))
        if len(rows) < 2:
            missing_members.append(stock_id)
            continue
        current = float(rows[-1]["close"])
        previous = float(rows[-2]["close"])
        high_sample = [float(row["close"]) for row in rows[-high_window:]]
        ma_sample = [float(row["close"]) for row in rows[-ma_window:]]
        if previous <= 0 or current <= 0 or not high_sample or not ma_sample:
            missing_members.append(stock_id)
            continue
        total += 1
        observed_members.append(stock_id)
        advancers += 1 if current > previous else 0
        above_ma += 1 if current >= sum(ma_sample) / len(ma_sample) else 0
        new_highs += 1 if current >= max(high_sample) else 0

    advancer_ratio = _ratio(advancers, total)
    above_ma_ratio = _ratio(above_ma, total)
    new_high_ratio = _ratio(new_highs, total)
    expected_count = len(expected_members)
    coverage_ratio = _ratio(total, expected_count)
    breadth_score = 50.0 if total == 0 else round(
        40.0 * advancer_ratio + 35.0 * above_ma_ratio + 25.0 * new_high_ratio,
        2,
    )
    return StockBreadthScore(
        theme=theme,
        breadth_score=breadth_score,
        advancers=advancers,
        total=total,
        expected=expected_count,
        advancer_ratio=advancer_ratio,
        above_ma_ratio=above_ma_ratio,
        new_high_ratio=new_high_ratio,
        coverage_ratio=coverage_ratio,
        members=observed_members,
        missing_members=missing_members,
        source=source,
    )


def rank_stock_breadth(
    stock_histories: dict[str, list[dict]],
    mapping: dict[str, list[str]] | None = None,
    source: str = "stock_daily",
) -> list[dict]:
    mapping = mapping or DEFAULT_THEME_STOCK_MAPPING
    rows = [
        calculate_stock_breadth(theme, stock_histories, stock_ids, source=source).as_dict()
        for theme, stock_ids in mapping.items()
    ]
    extra_by_theme: dict[str, list[str]] = {}
    mapped = {stock for stocks in mapping.values() for stock in stocks}
    for stock_id in stock_histories:
        if stock_id not in mapped:
            extra_by_theme.setdefault(theme_for_stock(stock_id), []).append(stock_id)
    for theme, stock_ids in extra_by_theme.items():
        if theme not in mapping:
            rows.append(calculate_stock_breadth(theme, stock_histories, stock_ids, source=source).as_dict())
    return sorted(
        rows,
        key=lambda item: (item["breadth_score"], item["coverage_ratio"], item["total"]),
        reverse=True,
    )


def stock_breadth_by_theme(
    stock_histories: dict[str, list[dict]],
    mapping: dict[str, list[str]] | None = None,
    source: str = "stock_daily",
) -> dict[str, dict]:
    return {row["theme"]: row for row in rank_stock_breadth(stock_histories, mapping=mapping, source=source)}


def stock_breadth_coverage(rows: list[dict]) -> dict:
    expected = sum(int(row.get("expected", 0)) for row in rows)
    observed = sum(int(row.get("total", 0)) for row in rows)
    return {
        "observed": observed,
        "expected": expected,
        "coverage_ratio": _ratio(observed, expected),
    }


def _sorted_rows(history: list[dict]) -> list[dict]:
    return sorted(history, key=lambda item: str(item["date"]))


def _ratio(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0
