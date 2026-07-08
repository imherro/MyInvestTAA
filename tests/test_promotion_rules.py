from engine.governance import build_promotion_report, evaluate_promotion


def _version_rows() -> list[dict]:
    return [
        {"version": "V3_TREND_RISK_ADJUSTED", "annual_return": 3.0, "max_drawdown": -14.0, "sharpe": 0.4, "calmar": 0.2},
        {"version": "V6_THEME_BREADTH_SELECTION", "annual_return": 4.0, "max_drawdown": -13.0, "sharpe": 0.5, "calmar": 0.3},
        {"version": "V7_STOCK_BREADTH_SELECTION", "annual_return": 4.5, "max_drawdown": -12.0, "sharpe": 0.6, "calmar": 0.4},
    ]


def _walk_forward() -> dict:
    return {
        "versions": {
            "V6_THEME_BREADTH_SELECTION": {"windows": 5, "win_rate": 0.8, "avg_alpha": 1.2, "drawdown_pass_rate": 0.8},
            "V7_STOCK_BREADTH_SELECTION": {"windows": 5, "win_rate": 0.8, "avg_alpha": 1.5, "drawdown_pass_rate": 0.8},
        }
    }


def test_evaluate_promotion_approves_when_all_checks_pass():
    result = evaluate_promotion(
        "V7",
        {"annual_return": 4, "max_drawdown": -10, "sharpe": 0.6},
        {"annual_return": 3, "max_drawdown": -12, "sharpe": 0.4},
        {"windows": 4, "win_rate": 0.75, "drawdown_pass_rate": 0.75},
    )

    assert result["promotion"] is True


def test_evaluate_promotion_rejects_missing_walk_forward():
    result = evaluate_promotion("V7", {"annual_return": 4, "max_drawdown": -10, "sharpe": 0.6})

    assert "rolling validation missing" in result["reasons"]


def test_evaluate_promotion_rejects_low_win_rate():
    result = evaluate_promotion(
        "V7",
        {"annual_return": 4, "max_drawdown": -10, "sharpe": 0.6},
        {"annual_return": 3, "max_drawdown": -12, "sharpe": 0.4},
        {"windows": 4, "win_rate": 0.25, "drawdown_pass_rate": 0.75},
    )

    assert "Walk-forward win rate below threshold" in result["reasons"]


def test_evaluate_promotion_rejects_worse_drawdown():
    result = evaluate_promotion(
        "V7",
        {"annual_return": 4, "max_drawdown": -20, "sharpe": 0.6},
        {"annual_return": 3, "max_drawdown": -12, "sharpe": 0.4},
        {"windows": 4, "win_rate": 0.75, "drawdown_pass_rate": 0.75},
    )

    assert "Max drawdown is worse than benchmark" in result["reasons"]


def test_evaluate_promotion_rejects_lower_sharpe():
    result = evaluate_promotion(
        "V7",
        {"annual_return": 4, "max_drawdown": -10, "sharpe": 0.3},
        {"annual_return": 3, "max_drawdown": -12, "sharpe": 0.4},
        {"windows": 4, "win_rate": 0.75, "drawdown_pass_rate": 0.75},
    )

    assert "Sharpe does not beat benchmark" in result["reasons"]


def test_evaluate_promotion_score_is_percent_passed():
    result = evaluate_promotion("V7", {}, {}, {})

    assert 0.0 <= result["promotion_score"] <= 100.0


def test_evaluate_promotion_records_validation_windows():
    result = evaluate_promotion("V7", {}, {}, {"windows": 2})

    assert result["validation_windows"] == 2


def test_evaluate_promotion_pending_when_failed():
    result = evaluate_promotion("V7", {}, {}, {})

    assert result["approval_status"] == "pending"


def test_build_promotion_report_returns_rows():
    report = build_promotion_report(_version_rows(), _walk_forward())

    assert len(report["rows"]) == 2


def test_build_promotion_report_records_benchmark():
    report = build_promotion_report(_version_rows(), _walk_forward())

    assert report["benchmark"] == "V3_TREND_RISK_ADJUSTED"


def test_build_promotion_report_selects_best_candidate():
    report = build_promotion_report(_version_rows(), _walk_forward())

    assert report["best_candidate"] == "V7_STOCK_BREADTH_SELECTION"


def test_build_promotion_report_records_approved_versions():
    report = build_promotion_report(_version_rows(), _walk_forward())

    assert "V7_STOCK_BREADTH_SELECTION" in report["approved_versions"]


def test_build_promotion_report_accepts_custom_candidates():
    report = build_promotion_report(_version_rows(), _walk_forward(), candidate_versions=["V6_THEME_BREADTH_SELECTION"])

    assert [row["version"] for row in report["rows"]] == ["V6_THEME_BREADTH_SELECTION"]


def test_build_promotion_report_ignores_missing_candidate():
    report = build_promotion_report(_version_rows(), _walk_forward(), candidate_versions=["MISSING"])

    assert report["rows"] == []


def test_build_promotion_report_row_contains_checks():
    report = build_promotion_report(_version_rows(), _walk_forward())

    assert "checks" in report["rows"][0]
