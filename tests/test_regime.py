from engine.regime import detect_market_regime


def test_detect_market_regime_bull():
    regime = detect_market_regime(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 103},
            {"date": "2024-03-01", "close": 106},
            {"date": "2024-04-01", "close": 110},
        ]
    )

    assert regime.state == "bull"
    assert regime.equity_limit == 90.0


def test_detect_market_regime_bear():
    regime = detect_market_regime(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 90},
            {"date": "2024-03-01", "close": 70},
            {"date": "2024-04-01", "close": 60},
        ]
    )

    assert regime.state == "bear"
    assert regime.equity_limit == 40.0


def test_detect_market_regime_bear_recovery():
    regime = detect_market_regime(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 75},
            {"date": "2024-03-01", "close": 78},
            {"date": "2024-04-01", "close": 85},
        ]
    )

    assert regime.state == "bear_recovery"
    assert regime.equity_limit == 70.0


def test_detect_market_regime_neutral_for_short_history():
    regime = detect_market_regime([{"date": "2024-01-01", "close": 100}])

    assert regime.state == "neutral"
    assert regime.confidence == 0.4


def test_detect_market_regime_bull_caution():
    regime = detect_market_regime(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 105},
            {"date": "2024-03-01", "close": 103},
            {"date": "2024-04-01", "close": 101},
        ]
    )

    assert regime.state == "bull_caution"
    assert regime.equity_limit == 75.0


def test_detect_market_regime_mixed_defaults_neutral():
    regime = detect_market_regime(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 90},
            {"date": "2024-03-01", "close": 96},
            {"date": "2024-04-01", "close": 93},
        ]
    )

    assert regime.state in {"neutral", "bear_recovery", "bull_caution"}


def test_detect_market_regime_rejects_non_positive_close():
    try:
        detect_market_regime(
            [
                {"date": "2024-01-01", "close": 100},
                {"date": "2024-02-01", "close": 0},
                {"date": "2024-03-01", "close": 90},
            ]
        )
    except ValueError as exc:
        assert "close must be positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
