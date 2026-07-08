from engine.theme import (
    DEFAULT_THEME_MAPPING,
    calculate_theme_momentum,
    load_theme_mapping,
    rank_theme_momentum,
    theme_for_asset,
    theme_momentum_by_theme,
)


def _history(values: list[float]) -> list[dict]:
    return [
        {"date": f"2024-{index + 1:02d}-01", "close": value}
        for index, value in enumerate(values)
    ]


def test_theme_mapping_covers_twenty_etfs():
    assert len(DEFAULT_THEME_MAPPING) == 20


def test_theme_for_asset_returns_known_theme():
    assert theme_for_asset("512760") == "semiconductor"


def test_theme_for_asset_returns_unclassified_for_unknown():
    assert theme_for_asset("UNKNOWN") == "unclassified"


def test_load_theme_mapping_returns_asset_theme_rows():
    rows = load_theme_mapping(["512760"])

    assert rows == [{"asset": "512760", "theme": "semiconductor"}]


def test_load_theme_mapping_defaults_to_all_known_assets():
    rows = load_theme_mapping()

    assert len(rows) == 20


def test_theme_momentum_returns_required_fields():
    score = calculate_theme_momentum("growth", {"A": _history([1, 1.2, 1.4])})

    assert {"theme", "momentum_score", "members", "windows"} <= set(score.as_dict())


def test_theme_momentum_rewards_positive_return():
    score = calculate_theme_momentum("growth", {"A": _history([1, 1.2])})

    assert score.momentum_score > 50


def test_theme_momentum_penalizes_negative_return():
    score = calculate_theme_momentum("growth", {"A": _history([1.2, 1.0])})

    assert score.momentum_score < 50


def test_theme_momentum_averages_members():
    score = calculate_theme_momentum("mixed", {"A": _history([1, 1.2]), "B": _history([1, 1.0])})

    assert score.weighted_return == 0.1


def test_theme_momentum_handles_short_history():
    score = calculate_theme_momentum("short", {"A": [{"date": "2024-01-01", "close": 1.0}]})

    assert score.momentum_score == 50.0


def test_theme_momentum_includes_all_windows():
    score = calculate_theme_momentum("growth", {"A": _history([1, 1.2])})

    assert set(score.windows) == {"return_21d", "return_63d", "return_126d", "return_252d"}


def test_theme_momentum_members_are_sorted():
    score = calculate_theme_momentum("growth", {"B": _history([1, 1.2]), "A": _history([1, 1.1])})

    assert score.members == ["A", "B"]


def test_theme_momentum_score_is_bounded_high():
    score = calculate_theme_momentum("growth", {"A": _history([1, 5])})

    assert score.momentum_score == 100.0


def test_theme_momentum_score_is_bounded_low():
    score = calculate_theme_momentum("growth", {"A": _history([5, 1])})

    assert score.momentum_score == 0.0


def test_rank_theme_momentum_returns_theme_rows():
    rows = rank_theme_momentum({"512760": _history([1, 2]), "510300": _history([1, 1.2])})

    assert {row["theme"] for row in rows} == {"semiconductor", "large_cap"}


def test_rank_theme_momentum_orders_stronger_theme_first():
    rows = rank_theme_momentum({"512760": _history([1, 2]), "510300": _history([1, 1.2])})

    assert rows[0]["theme"] == "semiconductor"


def test_rank_theme_momentum_assigns_rank():
    rows = rank_theme_momentum({"512760": _history([1, 2]), "510300": _history([1, 1.2])})

    assert rows[0]["rank"] == 1


def test_rank_theme_momentum_top_percentile_is_100():
    rows = rank_theme_momentum({"512760": _history([1, 2]), "510300": _history([1, 1.2])})

    assert rows[0]["momentum_score"] == 100.0


def test_rank_theme_momentum_single_theme_scores_100():
    rows = rank_theme_momentum({"512760": _history([1, 2])})

    assert rows[0]["momentum_score"] == 100.0


def test_theme_momentum_by_theme_returns_lookup():
    lookup = theme_momentum_by_theme({"512760": _history([1, 2])})

    assert lookup["semiconductor"]["theme"] == "semiconductor"
