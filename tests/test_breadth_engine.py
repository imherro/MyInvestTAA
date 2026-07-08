from engine.breadth import calculate_theme_breadth, rank_theme_breadth, theme_breadth_by_theme


def _history(values: list[float]) -> list[dict]:
    return [
        {"date": f"2024-{index + 1:02d}-01", "close": value}
        for index, value in enumerate(values)
    ]


def test_theme_breadth_returns_required_fields():
    score = calculate_theme_breadth("growth", {"A": _history([1, 1.2])})

    assert {"theme", "breadth_score", "advancers", "total"} <= set(score.as_dict())


def test_theme_breadth_counts_advancers():
    score = calculate_theme_breadth("growth", {"A": _history([1, 1.2]), "B": _history([1, 0.9])})

    assert score.advancers == 1


def test_theme_breadth_counts_total_valid_members():
    score = calculate_theme_breadth("growth", {"A": _history([1, 1.2]), "B": [{"date": "2024-01-01", "close": 1.0}]})

    assert score.total == 1


def test_theme_breadth_advancer_ratio():
    score = calculate_theme_breadth("growth", {"A": _history([1, 1.2]), "B": _history([1, 0.9])})

    assert score.advancer_ratio == 0.5


def test_theme_breadth_new_high_ratio():
    score = calculate_theme_breadth("growth", {"A": _history([1, 1.2]), "B": _history([1.1, 1.0])})

    assert score.new_high_ratio == 0.5


def test_theme_breadth_above_ma_ratio():
    score = calculate_theme_breadth("growth", {"A": _history([1, 1.2]), "B": _history([1.1, 1.0])})

    assert score.above_ma_ratio == 0.5


def test_theme_breadth_score_combines_components():
    score = calculate_theme_breadth("growth", {"A": _history([1, 1.2])})

    assert score.breadth_score == 100.0


def test_theme_breadth_handles_empty_members():
    score = calculate_theme_breadth("growth", {})

    assert score.breadth_score == 0.0


def test_theme_breadth_handles_short_members():
    score = calculate_theme_breadth("growth", {"A": [{"date": "2024-01-01", "close": 1.0}]})

    assert score.total == 0


def test_rank_theme_breadth_returns_rows():
    rows = rank_theme_breadth({"512760": _history([1, 2]), "510300": _history([1, 1.2])})

    assert {row["theme"] for row in rows} == {"semiconductor", "large_cap"}


def test_rank_theme_breadth_orders_by_score():
    rows = rank_theme_breadth({"512760": _history([1, 2]), "510300": _history([2, 1])})

    assert rows[0]["theme"] == "semiconductor"


def test_theme_breadth_by_theme_returns_lookup():
    lookup = theme_breadth_by_theme({"512760": _history([1, 2])})

    assert lookup["semiconductor"]["breadth_score"] == 100.0


def test_theme_breadth_score_can_be_partial():
    score = calculate_theme_breadth("growth", {"A": _history([1, 1.2]), "B": _history([1.2, 1.0])})

    assert score.breadth_score == 50.0


def test_theme_breadth_rows_include_ratios():
    row = rank_theme_breadth({"512760": _history([1, 2])})[0]

    assert {"advancer_ratio", "new_high_ratio", "above_ma_ratio"} <= set(row)
