from engine.stock_breadth import (
    calculate_stock_breadth,
    load_stock_theme_mapping,
    rank_stock_breadth,
    stock_breadth_by_theme,
    stock_breadth_coverage,
    stock_theme_universe,
    stocks_for_theme,
    theme_for_stock,
)


def _history(values: list[float]) -> list[dict]:
    return [
        {"date": f"2024-01-{index + 1:02d}", "close": value}
        for index, value in enumerate(values)
    ]


def test_load_stock_theme_mapping_returns_rows():
    rows = load_stock_theme_mapping(["semiconductor"])

    assert rows[0] == {"stock": "688981.SH", "theme": "semiconductor"}


def test_stocks_for_theme_returns_copy():
    rows = stocks_for_theme("semiconductor")
    rows.append("BAD")

    assert "BAD" not in stocks_for_theme("semiconductor")


def test_theme_for_stock_matches_full_code():
    assert theme_for_stock("688981.SH") == "innovation"


def test_theme_for_stock_matches_short_code():
    assert theme_for_stock("688981") == "innovation"


def test_theme_for_stock_returns_unclassified_for_unknown():
    assert theme_for_stock("NOPE") == "unclassified"


def test_stock_theme_universe_is_unique():
    universe = stock_theme_universe()

    assert len(universe) == len(set(universe))


def test_calculate_stock_breadth_counts_advancers():
    result = calculate_stock_breadth(
        "custom",
        {"A": _history([1, 2]), "B": _history([2, 1])},
        ["A", "B"],
    )

    assert result.advancer_ratio == 0.5


def test_calculate_stock_breadth_counts_above_ma():
    result = calculate_stock_breadth(
        "custom",
        {"A": _history([1, 2, 3]), "B": _history([3, 2, 1])},
        ["A", "B"],
        ma_window=3,
    )

    assert result.above_ma_ratio == 0.5


def test_calculate_stock_breadth_counts_new_highs():
    result = calculate_stock_breadth(
        "custom",
        {"A": _history([1, 2, 3]), "B": _history([3, 2, 1])},
        ["A", "B"],
        high_window=3,
    )

    assert result.new_high_ratio == 0.5


def test_calculate_stock_breadth_scores_weighted_components():
    result = calculate_stock_breadth(
        "custom",
        {"A": _history([1, 2, 3]), "B": _history([3, 2, 1])},
        ["A", "B"],
        ma_window=3,
        high_window=3,
    )

    assert result.breadth_score == 50.0


def test_calculate_stock_breadth_records_coverage():
    result = calculate_stock_breadth("custom", {"A": _history([1, 2])}, ["A", "B"])

    assert result.coverage_ratio == 0.5


def test_calculate_stock_breadth_lists_missing_members():
    result = calculate_stock_breadth("custom", {"A": _history([1, 2])}, ["A", "B"])

    assert result.missing_members == ["B"]


def test_calculate_stock_breadth_returns_neutral_when_no_data():
    result = calculate_stock_breadth("custom", {}, ["A"])

    assert result.breadth_score == 50.0


def test_calculate_stock_breadth_uses_default_theme_members():
    result = calculate_stock_breadth("government_bond", {"A": _history([1, 2])})

    assert result.expected == 0


def test_calculate_stock_breadth_preserves_source():
    result = calculate_stock_breadth("custom", {"A": _history([1, 2])}, ["A"], source="test")

    assert result.source == "test"


def test_calculate_stock_breadth_ignores_invalid_prices():
    result = calculate_stock_breadth("custom", {"A": _history([1, 0])}, ["A"])

    assert result.total == 0


def test_calculate_stock_breadth_as_dict_contains_ratios():
    row = calculate_stock_breadth("custom", {"A": _history([1, 2])}, ["A"]).as_dict()

    assert {"advancer_ratio", "above_ma_ratio", "new_high_ratio"} <= set(row)


def test_rank_stock_breadth_returns_theme_rows():
    rows = rank_stock_breadth({"688981.SH": _history([1, 2])})

    assert any(row["theme"] == "innovation" for row in rows)


def test_rank_stock_breadth_sorts_by_score():
    rows = rank_stock_breadth(
        {"A": _history([1, 2, 3]), "B": _history([3, 2, 1])},
        mapping={"strong": ["A"], "weak": ["B"]},
    )

    assert rows[0]["theme"] == "strong"


def test_stock_breadth_by_theme_indexes_rows():
    result = stock_breadth_by_theme({"A": _history([1, 2])}, mapping={"custom": ["A"]})

    assert result["custom"]["breadth_score"] == 100.0


def test_stock_breadth_coverage_sums_rows():
    rows = [
        calculate_stock_breadth("a", {"A": _history([1, 2])}, ["A", "B"]).as_dict(),
        calculate_stock_breadth("b", {"C": _history([1, 2])}, ["C"]).as_dict(),
    ]

    assert stock_breadth_coverage(rows) == {"observed": 2, "expected": 3, "coverage_ratio": 0.6667}


def test_rank_stock_breadth_keeps_empty_themes():
    rows = rank_stock_breadth({}, mapping={"empty": ["A"]})

    assert rows[0]["theme"] == "empty"


def test_stock_breadth_by_theme_preserves_source():
    result = stock_breadth_by_theme({"A": _history([1, 2])}, mapping={"custom": ["A"]}, source="unit")

    assert result["custom"]["source"] == "unit"
