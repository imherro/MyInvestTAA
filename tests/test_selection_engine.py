from engine.selection import (
    calculate_relative_strength,
    compare_selection_attribution,
    rank_relative_strength,
)


def _history(values: list[float], start_day: int = 1) -> list[dict]:
    return [
        {"date": f"2024-01-{start_day + index:02d}", "close": value}
        for index, value in enumerate(values)
    ]


def _calendar_history(values: list[float]) -> list[dict]:
    return [
        {"date": f"2024-{index + 1:02d}-01", "close": value}
        for index, value in enumerate(values)
    ]


def test_relative_strength_returns_required_fields():
    score = calculate_relative_strength("A", _calendar_history([1, 2, 3]), _calendar_history([1, 1.5, 2]))

    assert {"asset", "benchmark", "strength_score", "windows"} <= set(score.as_dict())


def test_relative_strength_rewards_asset_outperformance():
    score = calculate_relative_strength("A", _calendar_history([1, 1.2, 1.5]), _calendar_history([1, 1.05, 1.1]))

    assert score.strength_score > 50


def test_relative_strength_penalizes_underperformance():
    score = calculate_relative_strength("A", _calendar_history([1, 1.05, 1.1]), _calendar_history([1, 1.2, 1.5]))

    assert score.strength_score < 50


def test_relative_strength_is_neutral_against_self_like_benchmark():
    history = _calendar_history([1, 1.1, 1.2])

    score = calculate_relative_strength("510300", history, history)

    assert score.strength_score == 50.0


def test_relative_strength_handles_missing_benchmark_history():
    score = calculate_relative_strength("A", _calendar_history([1, 1.2]), [])

    assert score.strength_score == 50.0


def test_relative_strength_short_history_marks_missing_windows():
    score = calculate_relative_strength("A", [{"date": "2024-01-01", "close": 1.0}], _calendar_history([1, 1.2]))

    assert all(window["asset_return"] is None for window in score.windows.values())


def test_relative_strength_includes_all_required_windows():
    score = calculate_relative_strength("A", _calendar_history([1, 1.1, 1.2]), _calendar_history([1, 1.05, 1.1]))

    assert set(score.windows) == {"return_21d", "return_63d", "return_126d", "return_252d"}


def test_relative_strength_uses_earliest_row_before_lookback_window():
    score = calculate_relative_strength("A", _history([1, 1.2], start_day=1), _history([1, 1.0], start_day=1))

    assert score.windows["return_21d"]["asset_return"] == 0.2


def test_relative_strength_score_is_bounded_high():
    score = calculate_relative_strength("A", _calendar_history([1, 5]), _calendar_history([1, 1]))

    assert score.strength_score == 100.0


def test_relative_strength_score_is_bounded_low():
    score = calculate_relative_strength("A", _calendar_history([5, 1]), _calendar_history([1, 5]))

    assert score.strength_score == 0.0


def test_rank_relative_strength_returns_rows_for_histories():
    rows = rank_relative_strength({"A": _calendar_history([1, 2]), "510300": _calendar_history([1, 1.2])})

    assert len(rows) == 2


def test_rank_relative_strength_orders_stronger_asset_first():
    rows = rank_relative_strength({
        "A": _calendar_history([1, 2]),
        "B": _calendar_history([1, 1.1]),
        "510300": _calendar_history([1, 1.2]),
    })

    assert rows[0]["asset"] == "A"


def test_rank_relative_strength_assigns_rank_numbers():
    rows = rank_relative_strength({"A": _calendar_history([1, 2]), "510300": _calendar_history([1, 1.2])})

    assert [row["rank"] for row in rows] == [1, 2]


def test_rank_relative_strength_top_percentile_is_100():
    rows = rank_relative_strength({"A": _calendar_history([1, 2]), "510300": _calendar_history([1, 1.2])})

    assert rows[0]["strength_score"] == 100.0


def test_rank_relative_strength_single_asset_scores_100():
    rows = rank_relative_strength({"A": _calendar_history([1, 2])})

    assert rows[0]["strength_score"] == 100.0


def test_rank_relative_strength_preserves_raw_strength_score():
    rows = rank_relative_strength({"A": _calendar_history([1, 2]), "510300": _calendar_history([1, 1.2])})

    assert "raw_strength_score" in rows[0]


def test_rank_relative_strength_handles_empty_input():
    assert rank_relative_strength({}) == []


def test_compare_selection_attribution_reports_old_and_new():
    report = compare_selection_attribution({"selection": -1.0}, {"selection": 0.5})

    assert report["selection"]["old"] == -1.0
    assert report["selection"]["new"] == 0.5


def test_compare_selection_attribution_marks_improvement():
    report = compare_selection_attribution({"selection": -1.0}, {"selection": 0.5})

    assert report["selection"]["improved"] is True


def test_compare_selection_attribution_marks_no_improvement():
    report = compare_selection_attribution({"selection": 0.5}, {"selection": -1.0})

    assert report["selection"]["improved"] is False


def test_compare_selection_attribution_accepts_custom_labels():
    report = compare_selection_attribution({"selection": 0.0}, {"selection": 0.1}, baseline="OLD", candidate="NEW")

    assert report["baseline"] == "OLD"
    assert report["candidate"] == "NEW"
