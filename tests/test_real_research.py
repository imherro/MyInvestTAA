from data_pipeline import build_dataset_version, build_real_performance_report
from storage import MarketDataRepository, connect_database


def test_build_dataset_version_uses_end_date_in_id():
    version = build_dataset_version("mock", "2016-01-01", "2026-07-08", ["510300"])

    assert version.dataset_id == "20260708_MOCK_CN_ETF"


def test_build_dataset_version_checksum_is_stable():
    one = build_dataset_version("mock", "2016-01-01", "2026-07-08", ["510300"])
    two = build_dataset_version("mock", "2016-01-01", "2026-07-08", ["510300"])

    assert one.checksum == two.checksum


def test_build_dataset_version_checksum_changes_with_assets():
    one = build_dataset_version("mock", "2016-01-01", "2026-07-08", ["510300"])
    two = build_dataset_version("mock", "2016-01-01", "2026-07-08", ["512890"])

    assert one.checksum != two.checksum


def test_real_performance_report_returns_required_sections():
    repository = MarketDataRepository(connect_database(":memory:"))

    report = build_real_performance_report(repository, provider_name="mock")

    assert {"data", "performance", "benchmark", "stability", "attribution"} <= set(report)


def test_real_performance_report_records_dataset_version():
    repository = MarketDataRepository(connect_database(":memory:"))

    report = build_real_performance_report(repository, provider_name="mock")

    assert report["data"]["dataset_version"]["dataset_id"].endswith("_MOCK_CN_ETF")


def test_real_performance_report_saves_dataset_version():
    repository = MarketDataRepository(connect_database(":memory:"))

    build_real_performance_report(repository, provider_name="mock")

    assert repository.list_dataset_versions()


def test_real_performance_report_includes_universe_count():
    repository = MarketDataRepository(connect_database(":memory:"))

    report = build_real_performance_report(repository, provider_name="mock")

    assert report["data"]["universe_asset_count"] >= 20


def test_real_performance_report_imports_mock_assets():
    repository = MarketDataRepository(connect_database(":memory:"))

    report = build_real_performance_report(repository, provider_name="mock")

    assert report["data"]["imported_asset_count"] == 7


def test_real_performance_report_performance_has_core_metrics():
    repository = MarketDataRepository(connect_database(":memory:"))

    report = build_real_performance_report(repository, provider_name="mock")

    assert {"annual_return", "max_drawdown", "sharpe", "calmar"} <= set(report["performance"])


def test_real_performance_report_stability_has_win_rate():
    repository = MarketDataRepository(connect_database(":memory:"))

    report = build_real_performance_report(repository, provider_name="mock")

    assert 0.0 <= report["stability"]["win_rate"] <= 1.0


def test_real_performance_report_benchmark_has_rows():
    repository = MarketDataRepository(connect_database(":memory:"))

    report = build_real_performance_report(repository, provider_name="mock")

    assert len(report["benchmark"]) >= 4


def test_real_performance_report_accepts_custom_asset_subset():
    repository = MarketDataRepository(connect_database(":memory:"))

    report = build_real_performance_report(
        repository,
        provider_name="mock",
        asset_ids=["510300", "512890", "511010", "518880"],
    )

    assert report["data"]["imported_asset_count"] == 4
