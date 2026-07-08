from engine.calendar import is_trading_day, previous_trading_day


def test_is_trading_day_true_for_weekday():
    assert is_trading_day("2024-01-02") is True


def test_is_trading_day_false_for_saturday():
    assert is_trading_day("2024-01-06") is False


def test_is_trading_day_false_for_sunday():
    assert is_trading_day("2024-01-07") is False


def test_is_trading_day_false_for_market_holiday():
    assert is_trading_day("2024-10-01") is False


def test_previous_trading_day_skips_weekend():
    assert previous_trading_day("2024-01-08") == "2024-01-05"


def test_previous_trading_day_skips_holiday():
    assert previous_trading_day("2024-10-08") == "2024-09-30"


def test_previous_trading_day_accepts_trading_day():
    assert previous_trading_day("2024-01-03") == "2024-01-02"


def test_is_trading_day_accepts_date_object():
    from datetime import date

    assert is_trading_day(date(2024, 1, 2)) is True
