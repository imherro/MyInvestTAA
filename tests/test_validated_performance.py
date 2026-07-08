from data_pipeline import build_validated_performance_report
from storage import MarketDataRepository, connect_database


ASSET_IDS = ["510300", "512890", "511010", "518880"]


def _report() -> dict:
    repository = MarketDataRepository(connect_database(":memory:"))
    return build_validated_performance_report(repository, provider_name="mock", asset_ids=ASSET_IDS)


def test_validated_performance_report_returns_top_level_sections():
    report = _report()

    assert {"dataset", "performance", "benchmark", "attribution", "friction", "stability"} <= set(report)


def test_validated_performance_report_records_dataset_version():
    report = _report()

    assert report["dataset"]["dataset_version"]["dataset_id"].endswith("_MOCK_CN_ETF")


def test_validated_performance_report_records_imported_asset_count():
    report = _report()

    assert report["dataset"]["imported_asset_count"] == len(ASSET_IDS)


def test_validated_performance_report_records_price_rows():
    report = _report()

    assert report["dataset"]["price_rows"] > 0


def test_validated_performance_report_records_quality_score():
    report = _report()

    assert report["dataset"]["quality_score"] >= 50


def test_validated_performance_report_records_strategy_performance():
    report = _report()

    assert {"annual_return", "max_drawdown", "sharpe", "calmar", "ending_value"} <= set(report["performance"])


def test_validated_performance_report_records_benchmark_rows():
    report = _report()

    assert report["benchmark"]
    assert {"strategy_id", "annual_return", "max_drawdown"} <= set(report["benchmark"][0])


def test_validated_performance_report_records_decision_attribution():
    report = _report()

    assert report["attribution"]["decision"]["strategy"] == "MyInvestTAA"


def test_validated_performance_report_records_performance_attribution():
    report = _report()

    assert report["attribution"]["performance"]["strategy"] == "MyInvestTAA"
    assert "top_contributors" in report["attribution"]["performance"]


def test_validated_performance_report_records_friction_assumptions():
    report = _report()

    assert {"transaction_cost", "slippage", "expense_ratio"} <= set(report["friction"])


def test_validated_performance_report_records_stability_metrics():
    report = _report()

    assert {"rolling_alpha", "win_rate", "windows"} <= set(report["stability"])


def test_validated_performance_report_saves_dataset_version():
    repository = MarketDataRepository(connect_database(":memory:"))
    report = build_validated_performance_report(repository, provider_name="mock", asset_ids=ASSET_IDS)
    dataset_id = report["dataset"]["dataset_version"]["dataset_id"]

    assert repository.get_dataset_version(dataset_id) is not None
