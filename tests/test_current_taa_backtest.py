from datetime import date, timedelta

from current_taa.model import run_research


def _dates(count):
    result = []
    current = date(2020, 1, 1)
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def _assets(count=6):
    return [{"asset_id": f"A{i}", "name": f"资产{i}", "category": "broad_base", "data_source": "test", "enabled": True} for i in range(count)]


def _prices(dates, count=6):
    return {
        f"A{i}": [{"date": value, "close": 100 * (1 + 0.0002 * (i + 1)) ** index} for index, value in enumerate(dates)]
        for i in range(count)
    }


def test_late_asset_does_not_truncate_research_history():
    dates = _dates(500)
    prices = _prices(dates)
    prices["A5"] = prices["A5"][200:]
    report = run_research(_assets(), prices, dates)
    assert report["period"]["start"] < prices["A5"][252]["date"]
    assert report["monthly_allocations"][0]["eligible_asset_count"] == 5
    assert report["monthly_allocations"][-1]["eligible_asset_count"] == 6


def test_new_asset_only_appears_after_its_own_12m_history():
    dates = _dates(500)
    prices = _prices(dates)
    prices["A5"] = prices["A5"][200:]
    report = run_research(_assets(), prices, dates)
    first_six = next(row for row in report["monthly_allocations"] if row["eligible_asset_count"] == 6)
    assert first_six["signal_date"] >= prices["A5"][252]["date"]


def test_signal_is_applied_on_next_trade_date():
    dates = _dates(320)
    report = run_research(_assets(5), _prices(dates, 5), dates)
    first = report["monthly_allocations"][0]
    assert dates.index(first["effective_date"]) == dates.index(first["signal_date"]) + 1


def test_same_inputs_produce_same_research_report():
    dates = _dates(320)
    assets = _assets(5)
    prices = _prices(dates, 5)
    assert run_research(assets, prices, dates) == run_research(assets, prices, dates)


def test_report_uses_current_product_name():
    dates = _dates(320)
    report = run_research(_assets(5), _prices(dates, 5), dates)
    assert report["model"] == "CURRENT_TAA"
    assert report["model_description"] == "趋势/回撤型多资产 TAA"
