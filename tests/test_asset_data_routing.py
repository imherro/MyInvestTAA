import pytest

from data.models import PriceBar
from data_provider.mock_provider import MockProvider
from data_provider.tushare_provider import TushareProvider
from engine.asset_registry import ExecutionAsset, ResearchAsset, get_asset_history


def _research_asset(data_api: str, asset_id: str = "A") -> ResearchAsset:
    return ResearchAsset(
        asset_id=asset_id,
        name="Asset",
        instrument_type="index",
        role="research",
        category="broad_base",
        sleeve="equity_core",
        provider="mock",
        data_api=data_api,
        return_basis="total_return",
        data_start_date=None,
        investable_start_date=None,
        eligible_for_allocation=True,
    )


class SpyProvider:
    name = "spy"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None, str | None]] = []

    def _record(self, method: str, asset_id: str, start: str | None, end: str | None) -> list[PriceBar]:
        self.calls.append((method, asset_id, start, end))
        return [PriceBar(asset_id, "2024-01-02", 1.0, source=self.name)]

    def get_index_history(self, asset_id: str, start: str | None = None, end: str | None = None):
        return self._record("get_index_history", asset_id, start, end)

    def get_sw_index_history(self, asset_id: str, start: str | None = None, end: str | None = None):
        return self._record("get_sw_index_history", asset_id, start, end)

    def get_price_history(self, asset_id: str, start: str | None = None, end: str | None = None):
        return self._record("get_price_history", asset_id, start, end)

    def get_stock_price_history(self, asset_id: str, start: str | None = None, end: str | None = None):
        return self._record("get_stock_price_history", asset_id, start, end)


@pytest.mark.parametrize(
    ("data_api", "method"),
    [
        ("index_daily", "get_index_history"),
        ("sw_daily", "get_sw_index_history"),
        ("fund_daily", "get_price_history"),
        ("daily", "get_stock_price_history"),
    ],
)
def test_get_asset_history_routes_by_data_api(data_api, method):
    provider = SpyProvider()
    asset = _research_asset(data_api, asset_id="ROUTE")

    bars = get_asset_history(provider, asset, start="2024-01-01", end="2024-01-31")

    assert bars[0].asset_id == "ROUTE"
    assert provider.calls == [(method, "ROUTE", "2024-01-01", "2024-01-31")]


def test_get_asset_history_routes_execution_fund_daily_to_price_history():
    provider = SpyProvider()
    asset = ExecutionAsset(
        asset_id="510300.SH",
        name="沪深300ETF",
        instrument_type="etf",
        role="execution",
        provider="mock",
        data_api="fund_daily",
        return_basis="qfq",
        data_start_date=None,
        investable_start_date=None,
    )

    get_asset_history(provider, asset)

    assert provider.calls[0][0] == "get_price_history"


def test_get_asset_history_rejects_unknown_data_api():
    provider = SpyProvider()
    asset = _research_asset("unknown")

    with pytest.raises(ValueError, match="unsupported data_api"):
        get_asset_history(provider, asset)


@pytest.mark.parametrize(
    "method",
    ["get_price_history", "get_index_history", "get_sw_index_history", "get_stock_price_history"],
)
def test_mock_provider_supports_all_history_routes(method):
    provider = MockProvider(assets=[], histories={"A": [{"date": "2024-01-02", "close": 1.0}]})

    bars = getattr(provider, method)("A")

    assert bars[0].asset_id == "A"
    assert bars[0].date == "2024-01-02"


def test_mock_provider_sw_index_history_filters_dates():
    provider = MockProvider(
        assets=[],
        histories={
            "801780.SI": [
                {"date": "2024-01-02", "close": 1.0},
                {"date": "2024-02-01", "close": 1.2},
            ]
        },
    )

    bars = provider.get_sw_index_history("801780.SI", start="2024-02-01", end="2024-02-01")

    assert len(bars) == 1
    assert bars[0].close == 1.2


class FakeFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self._rows


class FakeTushareClient:
    def __init__(self):
        self.calls = []

    def sw_daily(self, **kwargs):
        self.calls.append(("sw_daily", kwargs))
        return FakeFrame(
            [
                {"trade_date": "20240103", "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1, "vol": 100},
                {"trade_date": "20240102", "open": 0.9, "high": 1.0, "low": 0.8, "close": 1.0, "vol": 90},
            ]
        )


def test_tushare_provider_sw_daily_uses_expected_parameters(monkeypatch):
    client = FakeTushareClient()
    provider = TushareProvider(token="unit")
    monkeypatch.setattr(provider, "_client", lambda: client)

    bars = provider.get_sw_index_history("801780.SI", start="2024-01-01", end="2024-01-31")

    assert client.calls == [
        (
            "sw_daily",
            {"ts_code": "801780.SI", "start_date": "20240101", "end_date": "20240131"},
        )
    ]
    assert [bar.date for bar in bars] == ["2024-01-02", "2024-01-03"]
    assert bars[0].return_type == "price"


class FakeIndexClient:
    def __init__(self):
        self.calls = []

    def index_daily(self, **kwargs):
        self.calls.append(("index_daily", kwargs))
        return FakeFrame([{"trade_date": "20240102", "close": 1.0}])


def test_tushare_provider_index_daily_still_uses_existing_method(monkeypatch):
    client = FakeIndexClient()
    provider = TushareProvider(token="unit")
    monkeypatch.setattr(provider, "_client", lambda: client)

    bars = provider.get_index_history("H00300.CSI", start="2024-01-01", end="2024-01-31")

    assert client.calls[0][0] == "index_daily"
    assert bars[0].asset_id == "H00300.CSI"
