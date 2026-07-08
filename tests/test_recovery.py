from engine.drawdown import detect_drawdown_events
from engine.recovery import analyze_recovery_events
from engine.recovery.statistics import median_number, round_optional


def test_analyze_recovery_events_counts_successful_recovery():
    prices = [
        {"date": "2020-01-01", "close": 100},
        {"date": "2020-02-01", "close": 70},
        {"date": "2021-02-01", "close": 105},
    ]
    events = detect_drawdown_events(prices)

    summary = analyze_recovery_events(events, prices, asset_id="demo")

    assert summary.asset_id == "demo"
    assert summary.event_count == 1
    assert summary.recovered_events == 1
    assert summary.recovery_probability == 1.0
    assert summary.sample_confidence == "low"
    assert summary.events[0].forward_return_1y_pct == 50.0


def test_analyze_recovery_events_counts_permanent_non_recovery():
    prices = [
        {"date": "2020-01-01", "close": 100},
        {"date": "2020-02-01", "close": 40},
        {"date": "2021-02-01", "close": 50},
    ]
    events = detect_drawdown_events(prices)

    summary = analyze_recovery_events(events, prices)

    assert summary.event_count == 1
    assert summary.recovered_events == 0
    assert summary.recovery_probability == 0.0
    assert summary.median_recovery_days is None
    assert summary.events[0].forward_return_1y_pct == 25.0


def test_analyze_recovery_events_handles_multiple_events():
    prices = [
        {"date": "2020-01-01", "close": 100},
        {"date": "2020-02-01", "close": 70},
        {"date": "2021-02-01", "close": 100},
        {"date": "2021-03-01", "close": 80},
        {"date": "2022-03-01", "close": 120},
    ]
    events = detect_drawdown_events(prices)

    summary = analyze_recovery_events(events, prices)

    assert summary.event_count == 2
    assert summary.recovered_events == 2
    assert summary.recovery_probability == 1.0
    assert summary.median_recovery_days is not None


def test_analyze_recovery_events_reports_medium_confidence():
    prices = [{"date": "2020-01-01", "close": 100}]
    for idx in range(1, 7):
        year = 2020 + idx
        prices.extend(
            [
                {"date": f"{year}-01-01", "close": 100 + idx},
                {"date": f"{year}-02-01", "close": 90},
                {"date": f"{year}-03-01", "close": 101 + idx},
            ]
        )
    events = detect_drawdown_events(prices)

    summary = analyze_recovery_events(events, prices)

    assert summary.event_count >= 5
    assert summary.sample_confidence == "medium"


def test_analyze_recovery_events_uses_bottom_date_forward_only():
    prices = [
        {"date": "2020-01-01", "close": 100},
        {"date": "2020-02-01", "close": 50},
        {"date": "2020-06-01", "close": 60},
        {"date": "2021-02-01", "close": 75},
        {"date": "2022-02-01", "close": 100},
        {"date": "2023-02-01", "close": 125},
    ]
    events = detect_drawdown_events(prices)

    summary = analyze_recovery_events(events, prices)
    event = summary.events[0]

    assert event.forward_return_1y_pct == 50.0
    assert event.forward_return_2y_pct == 100.0
    assert event.forward_return_3y_pct == 150.0


def test_analyze_recovery_events_marks_missing_forward_windows():
    prices = [
        {"date": "2020-01-01", "close": 100},
        {"date": "2020-02-01", "close": 70},
        {"date": "2020-06-01", "close": 80},
    ]
    events = detect_drawdown_events(prices)

    summary = analyze_recovery_events(events, prices)

    assert summary.events[0].forward_return_1y_pct is None
    assert summary.median_forward_return_1y_pct is None


def test_median_number_ignores_none_values():
    assert median_number([None, 10, 30, None, 20]) == 20


def test_median_number_handles_even_count():
    assert median_number([10, 30]) == 20


def test_round_optional_preserves_none():
    assert round_optional(None) is None
    assert round_optional(1.23456, 2) == 1.23
