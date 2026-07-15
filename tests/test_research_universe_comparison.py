import pytest

from backtest.research.data_loader import build_mock_research_price_dataset
from backtest.research.universe_comparison import build_research_universe_comparison
from engine.asset_registry import load_research_universe


def _eligible_assets():
    return [asset for asset in load_research_universe() if asset.eligible_for_allocation]


def test_comparison_uses_common_period_and_reports_added_asset_selection():
    assets = _eligible_assets()
    prices = build_mock_research_price_dataset(assets, periods=700)

    report = build_research_universe_comparison(assets, prices, "480092.CNI")

    assert report["available"] is True
    assert report["baseline_universe_count"] == len(assets) - 1
    assert report["candidate_universe_count"] == len(assets)
    assert report["comparison_period"]["trading_days"] == len(report["candidate"]["equity_curve"])
    assert report["baseline"]["equity_curve"][0]["value"] == 1.0
    assert report["candidate"]["equity_curve"][0]["value"] == 1.0
    assert report["selection_impact"]["total_candidate_months"] > 0


def test_comparison_rejects_unknown_added_asset():
    assets = _eligible_assets()
    prices = build_mock_research_price_dataset(assets, periods=700)

    with pytest.raises(ValueError, match="unknown added research asset"):
        build_research_universe_comparison(assets, prices, "UNKNOWN")
