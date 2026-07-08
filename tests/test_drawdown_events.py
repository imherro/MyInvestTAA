from engine.drawdown import calculate_drawdown_percentile, detect_drawdown_events


def test_detect_drawdown_events_returns_empty_for_monotonic_rise():
    events = detect_drawdown_events(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 110},
            {"date": "2024-03-01", "close": 120},
        ]
    )

    assert events == []


def test_detect_drawdown_events_handles_single_recovered_crash():
    events = detect_drawdown_events(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 70},
            {"date": "2024-03-01", "close": 80},
            {"date": "2024-04-01", "close": 101},
        ]
    )

    assert len(events) == 1
    event = events[0]
    assert event.peak_date == "2024-01-01"
    assert event.bottom_date == "2024-02-01"
    assert event.recovery_date == "2024-04-01"
    assert event.drawdown_pct == -30.0
    assert event.is_recovered is True


def test_detect_drawdown_events_handles_ongoing_bear_market():
    events = detect_drawdown_events(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 80},
            {"date": "2024-03-01", "close": 50},
            {"date": "2024-04-01", "close": 20},
        ]
    )

    assert len(events) == 1
    assert events[0].bottom_date == "2024-04-01"
    assert events[0].drawdown_pct == -80.0
    assert events[0].recovery_date is None
    assert events[0].is_recovered is False


def test_detect_drawdown_events_handles_v_shaped_recovery():
    events = detect_drawdown_events(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 60},
            {"date": "2024-03-01", "close": 100},
        ]
    )

    assert len(events) == 1
    assert events[0].drawdown_pct == -40.0
    assert events[0].recovery_date == "2024-03-01"


def test_calculate_drawdown_percentile_uses_event_distribution():
    events = detect_drawdown_events(
        [
            {"date": "2024-01-01", "close": 100},
            {"date": "2024-02-01", "close": 90},
            {"date": "2024-03-01", "close": 101},
            {"date": "2024-04-01", "close": 80},
            {"date": "2024-05-01", "close": 110},
            {"date": "2024-06-01", "close": 55},
        ]
    )

    pressure = calculate_drawdown_percentile(events, -25)

    assert pressure["event_count"] == 3
    assert pressure["percentile"] == 0.6667
    assert pressure["zone"] == "medium"

