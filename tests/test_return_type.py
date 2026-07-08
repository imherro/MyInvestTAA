from data.models import PriceBar
from data_pipeline.importer import build_provider
from data_pipeline.normalizer import price_bars_to_history, stored_prices_to_history
from data_provider.mock_provider import MockProvider
from data_provider.tushare_provider import TushareProvider, _price_bars_from_frame
from storage import MarketDataRepository, StoredPrice, connect_database


class _Frame:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def to_dict(self, orient: str) -> list[dict]:
        assert orient == "records"
        return self._rows


def test_price_bar_default_return_type_is_price():
    assert PriceBar("A", "2024-01-01", 1.0).return_type == "price"


def test_price_bar_from_mapping_reads_return_type():
    bar = PriceBar.from_mapping("A", {"date": "2024-01-01", "close": 1.0, "return_type": "total_return"})

    assert bar.return_type == "total_return"


def test_price_bar_as_dict_includes_return_type():
    payload = PriceBar("A", "2024-01-01", 1.0, return_type="qfq").as_dict()

    assert payload["return_type"] == "qfq"


def test_normalizers_preserve_return_type():
    bars = price_bars_to_history([PriceBar("A", "2024-01-01", 1.0, return_type="hfq")])
    prices = stored_prices_to_history([StoredPrice("A", "2024-01-01", 1.0, "mock", return_type="hfq")])

    assert bars[0]["return_type"] == "hfq"
    assert prices[0]["return_type"] == "hfq"


def test_repository_persists_return_type():
    repository = MarketDataRepository(connect_database(":memory:"))

    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.0, return_type="total_return")])

    assert repository.get_price_history("A")[0].return_type == "total_return"


def test_repository_all_histories_include_return_type():
    repository = MarketDataRepository(connect_database(":memory:"))

    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.0, return_type="qfq")])

    assert repository.get_all_price_histories()["A"][0]["return_type"] == "qfq"


def test_build_provider_passes_return_type_to_mock():
    provider = build_provider("mock", return_type="total_return")

    assert provider.return_type == "total_return"


def test_mock_provider_marks_return_type_on_bars():
    provider = MockProvider(assets=[], histories={"A": [{"date": "2024-01-01", "close": 1.0}]}, return_type="qfq")

    bar = provider.get_price_history("A")[0]

    assert bar.return_type == "qfq"
    assert bar.adjust_type == "qfq"


def test_tushare_frame_parser_marks_return_type():
    frame = _Frame([{"trade_date": "20240101", "close": 1.0}])

    bar = _price_bars_from_frame("510300", frame, return_type="total_return")[0]

    assert bar.return_type == "total_return"
    assert bar.adjust_type == "total_return"


def test_tushare_status_reports_return_type(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    assert TushareProvider(return_type="hfq").provider_status()["return_type"] == "hfq"
