from engine.governance import build_strategy_selection_report


def _version_rows() -> list[dict]:
    return [
        {
            "version": "V3_TREND_RISK_ADJUSTED",
            "annual_return": 3.0,
            "max_drawdown": -14.0,
            "sharpe": 0.4,
            "calmar": 0.2,
        },
        {
            "version": "V6_THEME_BREADTH_SELECTION",
            "annual_return": 4.2,
            "max_drawdown": -10.0,
            "sharpe": 0.7,
            "calmar": 0.42,
        },
        {
            "version": "V9_EXPOSURE_OPTIMIZED",
            "annual_return": 4.0,
            "max_drawdown": -11.0,
            "sharpe": 0.65,
            "calmar": 0.36,
        },
    ]


def _walk_forward() -> dict:
    return {
        "versions": {
            "V6_THEME_BREADTH_SELECTION": {
                "windows": 5,
                "win_rate": 0.8,
                "avg_alpha": 1.2,
                "min_alpha": -1.0,
                "drawdown_pass_rate": 0.8,
            },
            "V9_EXPOSURE_OPTIMIZED": {
                "windows": 5,
                "win_rate": 0.6,
                "avg_alpha": 0.8,
                "min_alpha": -2.5,
                "drawdown_pass_rate": 1.0,
            },
        }
    }


def test_strategy_selection_handles_empty_rows():
    report = build_strategy_selection_report([], {"versions": {}})

    assert report == {
        "winner": None,
        "confidence": 0.0,
        "rows": [],
        "production_version": "V3_TREND_RISK_ADJUSTED",
    }


def test_strategy_selection_returns_winner_and_confidence():
    report = build_strategy_selection_report(_version_rows(), _walk_forward())

    assert report["winner"] == "V6_THEME_BREADTH_SELECTION"
    assert report["confidence"] > 0.0


def test_strategy_selection_keeps_production_version():
    report = build_strategy_selection_report(_version_rows(), _walk_forward(), production_version="V3")

    assert report["production_version"] == "V3"


def test_strategy_selection_rows_are_sorted_by_score():
    report = build_strategy_selection_report(_version_rows(), _walk_forward())
    scores = [row["production_score"] for row in report["rows"]]

    assert scores == sorted(scores, reverse=True)


def test_strategy_selection_row_contains_required_metrics():
    report = build_strategy_selection_report(_version_rows(), _walk_forward())
    row = report["rows"][0]

    assert {
        "version",
        "production_score",
        "annual_return",
        "max_drawdown",
        "sharpe",
        "calmar",
        "walk_forward_win_rate",
        "walk_forward_avg_alpha",
        "walk_forward_min_alpha",
        "stability_score",
    } <= set(row)


def test_strategy_selection_uses_walk_forward_win_rate():
    report = build_strategy_selection_report(_version_rows(), _walk_forward())
    v6 = next(row for row in report["rows"] if row["version"] == "V6_THEME_BREADTH_SELECTION")

    assert v6["walk_forward_win_rate"] == 0.8


def test_strategy_selection_records_worst_window():
    report = build_strategy_selection_report(_version_rows(), _walk_forward())
    v9 = next(row for row in report["rows"] if row["version"] == "V9_EXPOSURE_OPTIMIZED")

    assert v9["walk_forward_min_alpha"] == -2.5


def test_strategy_selection_rewards_lower_drawdown():
    rows = [
        {"version": "LOW_DD", "annual_return": 3.0, "max_drawdown": -5.0, "sharpe": 0.5, "calmar": 0.3},
        {"version": "HIGH_DD", "annual_return": 3.0, "max_drawdown": -20.0, "sharpe": 0.5, "calmar": 0.3},
    ]

    report = build_strategy_selection_report(rows, {"versions": {}})

    assert report["rows"][0]["version"] == "LOW_DD"


def test_strategy_selection_rewards_higher_calmar_when_other_inputs_match():
    rows = [
        {"version": "LOW_CALMAR", "annual_return": 3.0, "max_drawdown": -10.0, "sharpe": 0.5, "calmar": 0.2},
        {"version": "HIGH_CALMAR", "annual_return": 3.0, "max_drawdown": -10.0, "sharpe": 0.5, "calmar": 0.5},
    ]

    report = build_strategy_selection_report(rows, {"versions": {}})

    assert report["rows"][0]["version"] == "HIGH_CALMAR"


def test_strategy_selection_rewards_higher_sharpe_when_other_inputs_match():
    rows = [
        {"version": "LOW_SHARPE", "annual_return": 3.0, "max_drawdown": -10.0, "sharpe": 0.2, "calmar": 0.3},
        {"version": "HIGH_SHARPE", "annual_return": 3.0, "max_drawdown": -10.0, "sharpe": 0.6, "calmar": 0.3},
    ]

    report = build_strategy_selection_report(rows, {"versions": {}})

    assert report["rows"][0]["version"] == "HIGH_SHARPE"


def test_strategy_selection_penalizes_single_window_collapse():
    rows = [
        {"version": "STABLE", "annual_return": 4.0, "max_drawdown": -10.0, "sharpe": 0.6, "calmar": 0.4},
        {"version": "COLLAPSE", "annual_return": 4.0, "max_drawdown": -10.0, "sharpe": 0.6, "calmar": 0.4},
    ]
    walk_forward = {
        "versions": {
            "STABLE": {"win_rate": 0.7, "drawdown_pass_rate": 0.7, "min_alpha": -1.0},
            "COLLAPSE": {"win_rate": 0.7, "drawdown_pass_rate": 0.7, "min_alpha": -8.0},
        }
    }

    report = build_strategy_selection_report(rows, walk_forward)

    assert report["rows"][0]["version"] == "STABLE"


def test_strategy_selection_defaults_missing_walk_forward_to_zero():
    report = build_strategy_selection_report(_version_rows(), {"versions": {}})
    v6 = next(row for row in report["rows"] if row["version"] == "V6_THEME_BREADTH_SELECTION")

    assert v6["walk_forward_win_rate"] == 0.0
    assert v6["stability_score"] == 0.0


def test_strategy_selection_confidence_is_score_ratio():
    report = build_strategy_selection_report(_version_rows(), _walk_forward())
    winner = next(row for row in report["rows"] if row["version"] == report["winner"])

    assert report["confidence"] == round(winner["production_score"] / 100.0, 4)


def test_strategy_selection_tie_breaks_by_sharpe_then_return():
    rows = [
        {"version": "LOW_RETURN", "annual_return": 3.0, "max_drawdown": -10.0, "sharpe": 0.5, "calmar": 0.3},
        {"version": "HIGH_RETURN", "annual_return": 4.0, "max_drawdown": -10.0, "sharpe": 0.5, "calmar": 0.3},
    ]

    report = build_strategy_selection_report(rows, {"versions": {}})

    assert report["winner"] == "HIGH_RETURN"
