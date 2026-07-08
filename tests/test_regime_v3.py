from engine.regime.v3 import detect_market_regime_v3


def _history(values: list[float]) -> list[dict]:
    return [{"date": f"2024-{index + 1:02d}-01", "close": value} for index, value in enumerate(values)]


def test_regime_v3_returns_neutral_for_short_history():
    report = detect_market_regime_v3(_history([1, 2]))

    assert report["state"] == "neutral"
    assert "insufficient history" in report["evidence"]


def test_regime_v3_detects_bull_trend():
    report = detect_market_regime_v3(_history([1, 1.05, 1.1, 1.15, 1.2, 1.25]), breadth=0.7)

    assert report["state"] == "bull"


def test_regime_v3_detects_bear_momentum():
    report = detect_market_regime_v3(_history([1.3, 1.2, 1.1, 1.0, 0.9, 0.8]), breadth=0.2)

    assert report["state"] == "bear"


def test_regime_v3_includes_evidence():
    report = detect_market_regime_v3(_history([1, 1.05, 1.1, 1.15, 1.2, 1.25]), breadth=0.7)

    assert report["evidence"]


def test_regime_v3_reports_breadth():
    report = detect_market_regime_v3(_history([1, 1, 1, 1, 1, 1]), breadth=0.55)

    assert report["breadth"] == 0.55


def test_regime_v3_reports_volatility_state():
    report = detect_market_regime_v3(_history([1, 1.01, 1.0, 1.02, 1.01, 1.03]))

    assert report["volatility_state"] in {"low", "high"}


def test_regime_v3_confidence_is_bounded():
    report = detect_market_regime_v3(_history([1, 1.05, 1.1, 1.15, 1.2, 1.25]), breadth=0.9)

    assert 0.4 <= report["confidence"] <= 0.9


def test_regime_v3_detects_bull_caution_for_soft_downtrend():
    report = detect_market_regime_v3(_history([1.0, 1.0, 1.0, 0.99, 0.98, 0.96]), breadth=0.45)

    assert report["state"] == "bull_caution"


def test_regime_v3_positive_trend_records_ma_evidence():
    report = detect_market_regime_v3(_history([1, 1.05, 1.1, 1.15, 1.2, 1.25]), breadth=0.7)

    assert "MA trend positive" in report["evidence"]


def test_regime_v3_momentum_is_rounded():
    report = detect_market_regime_v3(_history([1, 1.03, 1.07, 1.1, 1.14, 1.18]))

    assert report["momentum"] == round(report["momentum"], 4)
