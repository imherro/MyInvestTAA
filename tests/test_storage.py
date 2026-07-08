from data.models import AssetMetadata, PriceBar
from storage import (
    MarketDataRepository,
    StoredBacktestResult,
    StoredDatasetVersion,
    StoredExperiment,
    StoredPrice,
    StoredSignal,
    connect_database,
    initialize_database,
)
from storage.models import StoredAsset


def test_connect_database_initializes_tables():
    connection = connect_database(":memory:")

    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

    assert {"assets", "prices", "signals", "backtest_results", "experiments"} <= {row["name"] for row in rows}


def test_initialize_database_is_idempotent():
    connection = connect_database(":memory:")

    initialize_database(connection)

    assert connection.execute("SELECT COUNT(*) AS count FROM assets").fetchone()["count"] == 0


def test_stored_asset_as_dict():
    asset = StoredAsset("A", "Asset A", "equity", "mock")

    assert asset.as_dict()["asset_id"] == "A"


def test_repository_upserts_and_lists_assets():
    repository = MarketDataRepository(connect_database(":memory:"))

    count = repository.upsert_assets([AssetMetadata("A", "Asset A", "equity")])

    assert count == 1
    assert repository.list_assets()[0].asset_id == "A"


def test_repository_updates_asset_on_conflict():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.upsert_asset(AssetMetadata("A", "Old", "equity"))
    repository.upsert_asset(AssetMetadata("A", "New", "bond"))

    asset = repository.get_asset("A")

    assert asset.name == "New"
    assert asset.asset_class == "bond"


def test_repository_get_missing_asset_returns_none():
    repository = MarketDataRepository(connect_database(":memory:"))

    assert repository.get_asset("UNKNOWN") is None


def test_stored_price_as_dict():
    price = StoredPrice("A", "2024-01-01", 1.0, "mock")

    assert price.as_dict()["close"] == 1.0
    assert price.as_dict()["return_type"] == "price"


def test_repository_upserts_prices_in_order():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.upsert_prices(
        [
            PriceBar("A", "2024-02-01", 1.1),
            PriceBar("A", "2024-01-01", 1.0),
        ]
    )

    history = repository.get_price_history("A")

    assert [item.date for item in history] == ["2024-01-01", "2024-02-01"]


def test_repository_updates_price_on_conflict():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.0)])
    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.2)])

    assert repository.get_price_history("A")[0].close == 1.2


def test_repository_updates_price_return_type_on_conflict():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.0, return_type="price")])
    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.0, return_type="total_return")])

    assert repository.get_price_history("A")[0].return_type == "total_return"


def test_repository_get_all_price_histories_groups_by_asset():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.upsert_prices([PriceBar("A", "2024-01-01", 1.0), PriceBar("B", "2024-01-01", 2.0)])

    histories = repository.get_all_price_histories()

    assert set(histories) == {"A", "B"}


def test_stored_signal_as_dict():
    signal = StoredSignal("2024-01-01", "A", 1, 2, 3, 4, "neutral")

    assert signal.as_dict()["opportunity_score"] == 4


def test_repository_upserts_and_lists_signals():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.upsert_signal(StoredSignal("2024-01-01", "A", 1, 2, 3, 4, "neutral"))

    assert repository.list_signals()[0].asset_id == "A"


def test_stored_backtest_result_as_dict():
    result = StoredBacktestResult("S", "P", {"annual_return": 1})

    assert result.as_dict()["metrics"]["annual_return"] == 1


def test_repository_saves_backtest_result_json():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.save_backtest_result(StoredBacktestResult("S", "P", {"annual_return": 1}))

    assert repository.list_backtest_results()[0].metrics["annual_return"] == 1


def test_stored_dataset_version_as_dict():
    version = StoredDatasetVersion("D", "mock", "now", "2024-01-01", "2024-12-31", 1, "abc")

    assert version.as_dict()["dataset_id"] == "D"


def test_repository_saves_dataset_version():
    repository = MarketDataRepository(connect_database(":memory:"))
    version = StoredDatasetVersion("D", "mock", "now", "2024-01-01", "2024-12-31", 1, "abc")

    repository.save_dataset_version(version)

    assert repository.get_dataset_version("D").checksum == "abc"


def test_repository_updates_dataset_version_on_conflict():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.save_dataset_version(StoredDatasetVersion("D", "mock", "now", "2024-01-01", "2024-12-31", 1, "abc"))
    repository.save_dataset_version(StoredDatasetVersion("D", "mock", "later", "2024-01-01", "2024-12-31", 2, "def"))

    version = repository.get_dataset_version("D")

    assert version.asset_count == 2
    assert version.checksum == "def"


def test_repository_get_missing_dataset_version_returns_none():
    repository = MarketDataRepository(connect_database(":memory:"))

    assert repository.get_dataset_version("missing") is None


def test_repository_lists_dataset_versions():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.save_dataset_version(StoredDatasetVersion("D1", "mock", "now", "2024-01-01", "2024-12-31", 1, "abc"))
    repository.save_dataset_version(StoredDatasetVersion("D2", "mock", "later", "2024-01-01", "2024-12-31", 1, "def"))

    assert len(repository.list_dataset_versions()) == 2


def test_stored_experiment_as_dict():
    experiment = StoredExperiment("E", "hash", "D", "now", {"annual_return": 1})

    assert experiment.as_dict()["result"]["annual_return"] == 1


def test_repository_saves_experiment():
    repository = MarketDataRepository(connect_database(":memory:"))
    experiment = StoredExperiment("E", "hash", "D", "now", {"annual_return": 1})

    repository.save_experiment(experiment)

    assert repository.get_experiment("E").result["annual_return"] == 1


def test_repository_updates_experiment_on_conflict():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.save_experiment(StoredExperiment("E", "hash1", "D1", "now", {"annual_return": 1}))
    repository.save_experiment(StoredExperiment("E", "hash2", "D2", "later", {"annual_return": 2}))

    experiment = repository.get_experiment("E")

    assert experiment.config_hash == "hash2"
    assert experiment.result["annual_return"] == 2


def test_repository_lists_experiments():
    repository = MarketDataRepository(connect_database(":memory:"))
    repository.save_experiment(StoredExperiment("E1", "hash1", "D1", "now", {}))
    repository.save_experiment(StoredExperiment("E2", "hash2", "D2", "later", {}))

    assert len(repository.list_experiments()) == 2


def test_repository_get_missing_experiment_returns_none():
    repository = MarketDataRepository(connect_database(":memory:"))

    assert repository.get_experiment("missing") is None
