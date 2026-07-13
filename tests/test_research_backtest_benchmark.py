import pytest

from backtest.research.benchmark import HS300_RESEARCH_ASSET_ID, build_research_benchmarks
from backtest.research.data_loader import build_mock_research_price_dataset
from backtest.research.engine import _aligned_price_rows, run_research_backtest
from backtest.research.metrics import build_metrics
from backtest.research.models import ResearchBacktestConfig
from backtest.research.universe import load_research_backtest_universe


ASSETS = load_research_backtest_universe()
PRICE_DATA = build_mock_research_price_dataset(ASSETS, periods=520)
ALIGNED = _aligned_price_rows(ASSETS, PRICE_DATA)
REPORT = run_research_backtest(ASSETS, PRICE_DATA)


def test_benchmark_builds_hs300_and_equal_weight_rows():
    benchmark = REPORT["benchmark"]

    assert benchmark["available"] is True
    assert {row["strategy"] for row in benchmark["rows"]} == {
        "RESEARCH_TAA_MVP",
        "HS300_RESEARCH_BUY_HOLD",
        "EQUAL_WEIGHT_RESEARCH",
    }


def test_benchmark_alpha_uses_annual_return_difference():
    rows = {row["strategy"]: row for row in REPORT["benchmark"]["rows"]}

    assert REPORT["benchmark"]["alpha"]["vs_hs300"] == pytest.approx(
        rows["RESEARCH_TAA_MVP"]["annual_return"] - rows["HS300_RESEARCH_BUY_HOLD"]["annual_return"],
        abs=1e-6,
    )


def test_benchmark_report_keeps_compact_metric_only_payload():
    assert "equity_curves" not in REPORT["benchmark"]


def test_benchmark_without_hs300_returns_explicit_warning():
    prices = {asset_id: values for asset_id, values in ALIGNED["prices"].items() if asset_id != HS300_RESEARCH_ASSET_ID}
    benchmark = build_research_benchmarks({"dates": ALIGNED["dates"], "prices": prices}, start_index=252, strategy_metrics=REPORT["metrics"])

    assert benchmark["alpha"]["vs_hs300"] is None
    assert any(HS300_RESEARCH_ASSET_ID in warning for warning in benchmark["warnings"])


def test_benchmark_outside_range_is_unavailable():
    benchmark = build_research_benchmarks(ALIGNED, start_index=len(ALIGNED["dates"]), strategy_metrics=REPORT["metrics"])

    assert benchmark["available"] is False


@pytest.mark.parametrize("asset_id", [asset.asset_id for asset in ASSETS])
def test_equal_weight_benchmark_uses_every_eligible_asset(asset_id):
    assert asset_id in ALIGNED["prices"]


@pytest.mark.parametrize("strategy", ["RESEARCH_TAA_MVP", "HS300_RESEARCH_BUY_HOLD", "EQUAL_WEIGHT_RESEARCH"])
def test_each_benchmark_row_contains_standard_metrics(strategy):
    row = next(row for row in REPORT["benchmark"]["rows"] if row["strategy"] == strategy)

    assert {"annual_return", "max_drawdown", "sharpe", "calmar"} <= set(row)
