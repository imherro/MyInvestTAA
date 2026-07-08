from __future__ import annotations

from data_pipeline.importer import build_provider, import_market_data
from storage import MarketDataRepository, connect_database


def run_import_job(
    provider_name: str,
    asset_ids: list[str],
    database_path: str | None = None,
    start: str | None = None,
    end: str | None = None,
    return_type: str = "price",
) -> dict:
    connection = connect_database(database_path)
    repository = MarketDataRepository(connection)
    provider = build_provider(provider_name, return_type=return_type)
    return import_market_data(
        provider,
        repository,
        asset_ids=asset_ids,
        start=start,
        end=end,
    )
