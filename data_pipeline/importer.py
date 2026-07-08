from __future__ import annotations

from datetime import UTC, datetime

from backtest.benchmark import compare_strategies
from backtest.taa import run_taa_backtest
from data.models import AssetMetadata, PriceBar
from data_pipeline.normalizer import price_bars_to_history
from data_provider import BaoStockProvider, MockProvider, TushareProvider
from engine.asset_repository import load_assets
from engine.attribution import analyze_attribution
from engine.data_quality import build_quality_summary
from storage import MarketDataRepository, StoredBacktestResult


def build_provider(provider_name: str, return_type: str = "price"):
    normalized = provider_name.lower()
    if normalized == "mock":
        return MockProvider(return_type=return_type)
    if normalized == "tushare":
        return TushareProvider(return_type=return_type)
    if normalized == "baostock":
        return BaoStockProvider(return_type=return_type)
    raise ValueError(f"unknown provider: {provider_name}")


def import_market_data(
    provider,
    repository: MarketDataRepository,
    asset_ids: list[str],
    start: str | None = None,
    end: str | None = None,
    min_quality_score: float = 50.0,
) -> dict:
    assets = _select_assets(provider.get_etf_list(), asset_ids)
    histories: dict[str, list[dict]] = {}
    imported_prices = 0

    for asset in assets:
        bars = provider.get_price_history(asset.asset_id, start=start, end=end)
        histories[asset.asset_id] = price_bars_to_history(bars)
        imported_prices += len(bars)

    quality = build_quality_summary(histories)
    failing = [
        report["asset_id"]
        for report in quality["reports"]
        if report["score"] < min_quality_score
    ]
    if failing:
        raise ValueError(f"quality gate failed for assets: {', '.join(failing)}")

    repository.upsert_assets(assets)
    for asset in assets:
        bars = [
            PriceBar.from_mapping(asset.asset_id, row, source=provider.name)
            for row in histories[asset.asset_id]
        ]
        repository.upsert_prices(bars)

    return {
        "provider": provider.name,
        "imported_assets": len(assets),
        "imported_prices": imported_prices,
        "quality": quality,
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def run_live_backtest_report(
    repository: MarketDataRepository,
    provider_name: str = "mock",
    asset_ids: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    return_type: str = "price",
) -> dict:
    if asset_ids is None:
        asset_ids = [asset["id"] for asset in load_assets()]
    provider = build_provider(provider_name, return_type=return_type)
    import_summary = import_market_data(provider, repository, asset_ids, start=start, end=end)
    histories = repository.get_all_price_histories()
    assets = [
        asset for asset in load_assets()
        if asset["id"] in histories
    ]
    quality = build_quality_summary(histories)
    backtest = run_taa_backtest(assets=assets, price_history=histories)
    comparison = compare_strategies(assets=assets, price_history=histories)
    attribution = analyze_attribution(backtest)
    repository.save_backtest_result(
        StoredBacktestResult(
            strategy=backtest["strategy"],
            period=f'{backtest["period"]["start"]}:{backtest["period"]["end"]}',
            metrics=backtest["metrics"],
        )
    )
    return {
        "data_source": provider.name,
        "updated_at": import_summary["updated_at"],
        "asset_count": import_summary["imported_assets"],
        "price_rows": import_summary["imported_prices"],
        "quality": quality,
        "backtest": backtest,
        "benchmark": comparison,
        "alpha": comparison["alpha"],
        "attribution": attribution,
    }


def _select_assets(assets: list[AssetMetadata], asset_ids: list[str]) -> list[AssetMetadata]:
    by_id: dict[str, AssetMetadata] = {}
    for asset in assets:
        by_id[asset.asset_id] = asset
        if "." in asset.asset_id:
            short_id = asset.asset_id.split(".", 1)[0]
            by_id[short_id] = AssetMetadata(
                asset_id=short_id,
                name=asset.name,
                asset_class=asset.asset_class,
                market=asset.market,
                source=asset.source,
            )
    missing = sorted(set(asset_ids) - set(by_id))
    if missing:
        raise ValueError(f"provider missing asset metadata: {missing[0]}")
    return [by_id[asset_id] for asset_id in asset_ids]
