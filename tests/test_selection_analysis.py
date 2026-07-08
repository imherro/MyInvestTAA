from engine.selection import build_selection_analysis, selection_reasons


def _score(**overrides) -> dict:
    base = {
        "id": "A",
        "name": "Asset A",
        "theme": "growth",
        "opportunity_score": 80.0,
        "relative_strength_score": 75.0,
        "theme_momentum_score": 80.0,
        "breadth_score": 70.0,
        "trend_score": 65.0,
        "quality_score": 70.0,
    }
    return base | overrides


def test_selection_reasons_reports_theme_momentum():
    assert "Theme momentum high" in selection_reasons(_score())


def test_selection_reasons_reports_breadth():
    assert "Breadth improving" in selection_reasons(_score())


def test_selection_reasons_reports_relative_strength():
    assert "Relative strength top tier" in selection_reasons(_score())


def test_selection_reasons_reports_trend():
    assert "Trend supportive" in selection_reasons(_score())


def test_selection_reasons_reports_quality():
    assert "Quality anchor acceptable" in selection_reasons(_score())


def test_selection_reasons_returns_mixed_when_no_signal_is_strong():
    reasons = selection_reasons(_score(relative_strength_score=40, theme_momentum_score=40, breadth_score=30, trend_score=20, quality_score=30))

    assert reasons == ["Mixed selection evidence"]


def test_build_selection_analysis_handles_empty_states():
    report = build_selection_analysis({"assumptions": {"score_version": "v6"}, "states": []})

    assert report["rows"] == []


def test_build_selection_analysis_returns_latest_scores():
    backtest = {
        "assumptions": {"score_version": "v6"},
        "states": [{"date": "2024-01-31", "signals": {"scores": [_score()]}}],
    }

    report = build_selection_analysis(backtest)

    assert report["rows"][0]["asset"] == "A"


def test_build_selection_analysis_respects_limit():
    backtest = {
        "assumptions": {"score_version": "v6"},
        "states": [{"date": "2024-01-31", "signals": {"scores": [_score(id="A"), _score(id="B")]}}],
    }

    report = build_selection_analysis(backtest, limit=1)

    assert len(report["rows"]) == 1


def test_build_selection_analysis_preserves_existing_reason():
    backtest = {
        "assumptions": {"score_version": "v6"},
        "states": [{"date": "2024-01-31", "signals": {"scores": [_score(selection_reason=["custom"])]}}],
    }

    report = build_selection_analysis(backtest)

    assert report["rows"][0]["selection_reason"] == ["custom"]
