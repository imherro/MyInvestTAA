from data.models import PriceBar
from data_provider.tushare_provider import (
    _from_tushare_date,
    _to_ts_code,
    _to_tushare_date,
)


def test_price_bar_from_mapping_converts_required_fields():
    bar = PriceBar.from_mapping("A", {"date": "2024-01-01", "close": "1.23"})

    assert bar.asset_id == "A"
    assert bar.close == 1.23


def test_price_bar_as_dict_excludes_missing_optional_fields():
    payload = PriceBar("A", "2024-01-01", 1.0).as_dict()

    assert "open" not in payload
    assert payload["source"] == "mock"


def test_price_bar_as_price_row_matches_engine_shape():
    row = PriceBar("A", "2024-01-01", 1.0).as_price_row()

    assert row == {"date": "2024-01-01", "close": 1.0}


def test_tushare_code_normalization_defaults_shanghai_for_etf():
    assert _to_ts_code("510300") == "510300.SH"


def test_tushare_date_conversion_round_trips():
    assert _from_tushare_date(_to_tushare_date("2024-01-31")) == "2024-01-31"
