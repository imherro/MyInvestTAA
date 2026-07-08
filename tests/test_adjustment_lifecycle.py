from datetime import date

import pytest

from backtest.taa import run_taa_backtest
from backtest.taa.engine import _assets_available_as_of
from data.models import PriceBar
from data_pipeline.normalizer import price_bars_to_history, stored_prices_to_history
from storage import MarketDataRepository, StoredPrice, connect_database


def _asset(asset_id: str, start_date: str = "2024-01-01", end_date: str | None = None, anchor_score: float = 80) -> dict:
    return {
        "id": asset_id,
        "name": asset_id,
        "category": "test",
        "anchor_score": anchor_score,
        "prices": [],
        "start_date": start_date,
        "end_date": end_date,
    }


def _history(values: list[tuple[str, float]]) -> list[dict]:
    return [{"date": item_date, "close": close} for item_date, close in values]


def test_price_bar_default_adjust_type_is_none():
    bar = PriceBar("A", "2024-01-01", 1.0)

    assert bar.adjust_type == "none"


def test_price_bar_from_mapping_reads_adjust_type():
    bar = PriceBar.from_mapping("A", {"date": "2024-01-01", "close": 1.0, "adjust_type": "qfq"})

    assert bar.adjust_type == "qfq"


def test_price_bar_from_mapping_reads_adjust_alias():
    bar = PriceBar.from_mapping("A", {"date": "2024-01-01", "close": 1.0, "adjust": "hfq"})

    assert bar.adjust_type == "hfq"


def test_price_bar_as_dict_includes_adjust_type():
    payload = PriceBar("A", "2024-01-01", 1.0, adjust_type="total_return").as_dict()

    assert payload["adjust_type"] == "total_return"


def test_price_bars_to_history_preserves_adjust_type():
    history = price_bars_to_history([PriceBar("A", "2024-01-01", 1.0, adjust_type="qfq")])

    assert history[0]["adjust_type"] == "qfq"


def test_stored_prices_to_history_preserves_adjust_type():
    history = stored_prices_to_history([StoredPrice("A", "2024-01-01", 1.0, "mock", adjust_type="hfq")])

    assert history[0]["adjust_type"] == "hfq"


def test_repository_persists_price_adjust_type():
    repository = MarketDataRepository(connect_database(":memory:"))

    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.0, source="mock", adjust_type="qfq")])

    assert repository.get_price_history("A")[0].adjust_type == "qfq"


def test_repository_updates_price_adjust_type_on_conflict():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.0, source="mock", adjust_type="none")])

    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.0, source="mock", adjust_type="total_return")])

    assert repository.get_price_history("A")[0].adjust_type == "total_return"


def test_repository_all_histories_include_adjust_type():
    repository = MarketDataRepository(connect_database(":memory:"))

    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.0, source="mock", adjust_type="qfq")])

    assert repository.get_all_price_histories()["A"][0]["adjust_type"] == "qfq"


def test_assets_available_as_of_includes_start_date_boundary():
    assets = [_asset("A", start_date="2024-01-31")]

    available = _assets_available_as_of(assets, date.fromisoformat("2024-01-31"))

    assert [item["id"] for item in available] == ["A"]


def test_assets_available_as_of_excludes_before_start_date():
    assets = [_asset("A", start_date="2024-02-01")]

    assert _assets_available_as_of(assets, date.fromisoformat("2024-01-31")) == []


def test_assets_available_as_of_includes_end_date_boundary():
    assets = [_asset("A", end_date="2024-01-31")]

    available = _assets_available_as_of(assets, date.fromisoformat("2024-01-31"))

    assert [item["id"] for item in available] == ["A"]


def test_assets_available_as_of_excludes_after_end_date():
    assets = [_asset("A", end_date="2024-01-31")]

    assert _assets_available_as_of(assets, date.fromisoformat("2024-02-29")) == []


def test_run_taa_backtest_filters_future_asset_from_scores():
    assets = [
        _asset("510300", anchor_score=50),
        _asset("EARLY", anchor_score=60),
        _asset("FUTURE", start_date="2024-04-01", anchor_score=100),
    ]
    history = {
        "510300": _history([("2024-01-31", 1.00), ("2024-02-29", 1.01), ("2024-03-31", 1.02), ("2024-04-30", 1.03)]),
        "EARLY": _history([("2024-01-31", 1.00), ("2024-02-29", 1.03), ("2024-03-31", 1.06), ("2024-04-30", 1.09)]),
        "FUTURE": _history([("2024-01-31", 1.00), ("2024-02-29", 1.10), ("2024-03-31", 1.20), ("2024-04-30", 1.30)]),
    }

    result = run_taa_backtest(assets=assets, price_history=history)
    feb_scores = result["states"][1]["signals"]["scores"]
    apr_scores = result["states"][-1]["signals"]["scores"]

    assert "FUTURE" not in {item["id"] for item in feb_scores}
    assert "FUTURE" in {item["id"] for item in apr_scores}


def test_run_taa_backtest_filters_ended_asset_from_scores():
    assets = [
        _asset("510300", anchor_score=50),
        _asset("ENDED", end_date="2024-02-29", anchor_score=100),
    ]
    history = {
        "510300": _history([("2024-01-31", 1.00), ("2024-02-29", 1.01), ("2024-03-31", 1.02)]),
        "ENDED": _history([("2024-01-31", 1.00), ("2024-02-29", 1.10), ("2024-03-31", 1.20)]),
    }

    result = run_taa_backtest(assets=assets, price_history=history)
    march_scores = result["states"][-1]["signals"]["scores"]

    assert "ENDED" not in {item["id"] for item in march_scores}


def test_run_taa_backtest_rejects_negative_slippage():
    with pytest.raises(ValueError):
        run_taa_backtest(slippage=-0.001)


def test_run_taa_backtest_rejects_negative_expense_ratio():
    with pytest.raises(ValueError):
        run_taa_backtest(expense_ratio=-0.001)


def test_run_taa_backtest_records_slippage_and_expense_ratio_assumptions():
    result = run_taa_backtest(slippage=0.002, expense_ratio=0.006)

    assert result["assumptions"]["slippage"] == 0.002
    assert result["assumptions"]["expense_ratio"] == 0.006


def test_run_taa_backtest_slippage_lowers_ending_value():
    without_slippage = run_taa_backtest(slippage=0.0)
    with_slippage = run_taa_backtest(slippage=0.02)

    assert with_slippage["metrics"]["ending_value"] <= without_slippage["metrics"]["ending_value"]


def test_run_taa_backtest_expense_ratio_lowers_ending_value():
    without_expense = run_taa_backtest(expense_ratio=0.0)
    with_expense = run_taa_backtest(expense_ratio=0.12)

    assert with_expense["metrics"]["ending_value"] <= without_expense["metrics"]["ending_value"]
