from engine.governance import build_final_strategy_report


def _version_rows() -> list[dict]:
    return [
        {"version": "V6_THEME_BREADTH_SELECTION", "annual_return": 4.6, "max_drawdown": -12.0, "sharpe": 0.59, "calmar": 0.38},
        {"version": "V7_STOCK_BREADTH_SELECTION", "annual_return": 4.4, "max_drawdown": -12.8, "sharpe": 0.57, "calmar": 0.34},
        {"version": "V10_ROBUST_EXPOSURE", "annual_return": 4.2, "max_drawdown": -10.5, "sharpe": 0.56, "calmar": 0.40},
    ]


def _walk_forward() -> dict:
    return {
        "versions": {
            "V6_THEME_BREADTH_SELECTION": {"win_rate": 0.375, "min_alpha": -2.5},
            "V7_STOCK_BREADTH_SELECTION": {"win_rate": 0.625, "min_alpha": -4.2},
            "V10_ROBUST_EXPOSURE": {"win_rate": 0.625, "min_alpha": -3.0},
        }
    }


def _robustness() -> dict:
    return {
        "version_scores": [
            {"version": "V6_THEME_BREADTH_SELECTION", "robustness_score": 55.0, "pass": True},
            {"version": "V7_STOCK_BREADTH_SELECTION", "robustness_score": 75.0, "pass": True},
            {"version": "V10_ROBUST_EXPOSURE", "robustness_score": 60.0, "pass": True},
        ]
    }


def test_final_strategy_handles_empty_rows():
    report = build_final_strategy_report([], {"versions": {}}, {"version_scores": []})

    assert report["production_candidate"] is None
    assert report["rows"] == []


def test_final_strategy_returns_candidate_and_confidence():
    report = build_final_strategy_report(_version_rows(), _walk_forward(), _robustness())

    assert report["candidate"] in {"V7_STOCK_BREADTH_SELECTION", "V10_ROBUST_EXPOSURE", "V6_THEME_BREADTH_SELECTION"}
    assert report["confidence"] > 0


def test_final_strategy_row_contains_required_fields():
    report = build_final_strategy_report(_version_rows(), _walk_forward(), _robustness())
    row = report["rows"][0]

    assert {
        "version",
        "production_score_v2",
        "walk_forward_win_rate",
        "walk_forward_min_alpha",
        "robustness_score",
        "checks",
    } <= set(row)


def test_final_strategy_rows_are_sorted_by_score():
    report = build_final_strategy_report(_version_rows(), _walk_forward(), _robustness())
    scores = [row["production_score_v2"] for row in report["rows"]]

    assert scores == sorted(scores, reverse=True)


def test_final_strategy_marks_top_row_as_highest_score():
    report = build_final_strategy_report(_version_rows(), _walk_forward(), _robustness())

    assert report["rows"][0]["checks"]["highest_score"] is True
    assert all(row["checks"]["highest_score"] is False for row in report["rows"][1:])


def test_final_strategy_requires_walk_forward_win_rate():
    walk_forward = {"versions": {"V7_STOCK_BREADTH_SELECTION": {"win_rate": 0.4, "min_alpha": -2.0}}}
    report = build_final_strategy_report(
        [{"version": "V7_STOCK_BREADTH_SELECTION", "annual_return": 4.0, "max_drawdown": -10, "sharpe": 0.6}],
        walk_forward,
        {"version_scores": [{"version": "V7_STOCK_BREADTH_SELECTION", "robustness_score": 90.0, "pass": True}]},
    )

    assert report["production_candidate"] is None
    assert report["rows"][0]["checks"]["walk_forward_win_rate"] is False


def test_final_strategy_requires_worst_window_above_threshold():
    walk_forward = {"versions": {"V7_STOCK_BREADTH_SELECTION": {"win_rate": 0.7, "min_alpha": -6.0}}}
    report = build_final_strategy_report(
        [{"version": "V7_STOCK_BREADTH_SELECTION", "annual_return": 4.0, "max_drawdown": -10, "sharpe": 0.6}],
        walk_forward,
        {"version_scores": [{"version": "V7_STOCK_BREADTH_SELECTION", "robustness_score": 90.0, "pass": True}]},
    )

    assert report["production_candidate"] is None
    assert report["rows"][0]["checks"]["worst_window"] is False


def test_final_strategy_requires_robustness_pass():
    report = build_final_strategy_report(
        [{"version": "V7_STOCK_BREADTH_SELECTION", "annual_return": 4.0, "max_drawdown": -10, "sharpe": 0.6}],
        {"versions": {"V7_STOCK_BREADTH_SELECTION": {"win_rate": 0.7, "min_alpha": -2.0}}},
        {"version_scores": [{"version": "V7_STOCK_BREADTH_SELECTION", "robustness_score": 90.0, "pass": False}]},
    )

    assert report["production_candidate"] is None
    assert report["rows"][0]["checks"]["robustness_pass"] is False


def test_final_strategy_approves_when_top_candidate_passes_all_rules():
    report = build_final_strategy_report(
        [{"version": "V7_STOCK_BREADTH_SELECTION", "annual_return": 4.0, "max_drawdown": -10, "sharpe": 0.6}],
        {"versions": {"V7_STOCK_BREADTH_SELECTION": {"win_rate": 0.7, "min_alpha": -2.0}}},
        {"version_scores": [{"version": "V7_STOCK_BREADTH_SELECTION", "robustness_score": 90.0, "pass": True}]},
    )

    assert report["production_candidate"] == "V7_STOCK_BREADTH_SELECTION"
    assert report["rows"][0]["final_rule_pass"] is True


def test_final_strategy_uses_custom_candidates():
    report = build_final_strategy_report(
        _version_rows(),
        _walk_forward(),
        _robustness(),
        candidate_versions=["V10_ROBUST_EXPOSURE"],
    )

    assert [row["version"] for row in report["rows"]] == ["V10_ROBUST_EXPOSURE"]


def test_final_strategy_preserves_production_version():
    report = build_final_strategy_report(_version_rows(), _walk_forward(), _robustness(), production_version="V3")

    assert report["production_version"] == "V3"


def test_final_strategy_reason_reports_failed_checks():
    report = build_final_strategy_report(
        [{"version": "V7_STOCK_BREADTH_SELECTION", "annual_return": 4.0, "max_drawdown": -10, "sharpe": 0.6}],
        {"versions": {"V7_STOCK_BREADTH_SELECTION": {"win_rate": 0.4, "min_alpha": -6.0}}},
        {"version_scores": [{"version": "V7_STOCK_BREADTH_SELECTION", "robustness_score": 90.0, "pass": False}]},
    )

    assert "Failed checks" in report["reason"][1]


def test_final_strategy_confidence_matches_top_score():
    report = build_final_strategy_report(_version_rows(), _walk_forward(), _robustness())

    assert report["confidence"] == round(report["rows"][0]["production_score_v2"] / 100.0, 4)
