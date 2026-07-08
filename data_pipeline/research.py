from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from backtest.evaluation import rolling_analysis
from data.universe import load_china_etf_universe, universe_asset_ids
from data_pipeline.importer import run_live_backtest_report
from engine.asset_repository import load_assets
from engine.performance_attribution import analyze_performance_contribution
from storage import MarketDataRepository, StoredDatasetVersion


def build_dataset_version(
    source: str,
    start_date: str,
    end_date: str,
    asset_ids: list[str],
    created_at: str | None = None,
) -> StoredDatasetVersion:
    if created_at is None:
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
    dataset_id = f"{end_date.replace('-', '')}_{source.upper()}_CN_ETF"
    checksum = _dataset_checksum(source, start_date, end_date, asset_ids)
    return StoredDatasetVersion(
        dataset_id=dataset_id,
        source=source,
        created_at=created_at,
        start_date=start_date,
        end_date=end_date,
        asset_count=len(asset_ids),
        checksum=checksum,
    )


def build_real_performance_report(
    repository: MarketDataRepository,
    provider_name: str = "mock",
    start_date: str = "2016-01-01",
    end_date: str = "2026-07-08",
    asset_ids: list[str] | None = None,
    return_type: str = "price",
) -> dict:
    if asset_ids is None:
        asset_ids = _default_asset_ids(provider_name)

    live = run_live_backtest_report(
        repository,
        provider_name=provider_name,
        asset_ids=asset_ids,
        start=start_date,
        end=end_date,
        return_type=return_type,
    )
    version = build_dataset_version(
        source=provider_name,
        start_date=start_date,
        end_date=end_date,
        asset_ids=asset_ids,
    )
    repository.save_dataset_version(version)
    stability = rolling_analysis(live["benchmark"])
    metrics = live["backtest"]["metrics"]
    return {
        "data": {
            "provider": provider_name,
            "dataset_version": version.as_dict(),
            "quality_score": live["quality"]["average_score"],
            "universe_asset_count": len(load_china_etf_universe()),
            "imported_asset_count": live["asset_count"],
            "price_rows": live["price_rows"],
            "return_type": return_type,
        },
        "performance": {
            "strategy": live["backtest"]["strategy"],
            "period": live["backtest"]["period"],
            "annual_return": metrics["annual_return"],
            "max_drawdown": metrics["max_drawdown"],
            "sharpe": metrics["sharpe"],
            "calmar": metrics["calmar"],
            "ending_value": metrics["ending_value"],
        },
        "benchmark": live["benchmark"]["rows"],
        "stability": {
            "rolling_alpha": stability["avg_alpha"],
            "win_rate": stability["rolling_win_rate"],
            "windows": stability["windows"],
        },
        "attribution": live["attribution"],
    }


def build_validated_performance_report(
    repository: MarketDataRepository,
    provider_name: str = "mock",
    start_date: str = "2016-01-01",
    end_date: str = "2026-07-08",
    asset_ids: list[str] | None = None,
    return_type: str = "price",
) -> dict:
    report = build_real_performance_report(
        repository=repository,
        provider_name=provider_name,
        start_date=start_date,
        end_date=end_date,
        asset_ids=asset_ids,
        return_type=return_type,
    )
    histories = repository.get_all_price_histories()
    live_backtest = run_live_backtest_report(
        repository,
        provider_name=provider_name,
        asset_ids=asset_ids or _default_asset_ids(provider_name),
        start=start_date,
        end=end_date,
        return_type=return_type,
    )["backtest"]
    performance_attribution = analyze_performance_contribution(
        backtest_result=live_backtest,
        price_history=histories,
    )
    return {
        "dataset": report["data"],
        "performance": report["performance"],
        "benchmark": report["benchmark"],
        "attribution": {
            "decision": report["attribution"],
            "performance": performance_attribution,
        },
        "friction": {
            "transaction_cost": live_backtest["assumptions"]["transaction_cost"],
            "slippage": live_backtest["assumptions"]["slippage"],
            "expense_ratio": live_backtest["assumptions"]["expense_ratio"],
        },
        "stability": report["stability"],
    }


def _default_asset_ids(provider_name: str) -> list[str]:
    if provider_name == "mock":
        return [asset["id"] for asset in load_assets()]
    return universe_asset_ids()


def _dataset_checksum(source: str, start_date: str, end_date: str, asset_ids: list[str]) -> str:
    payload = {
        "source": source,
        "start_date": start_date,
        "end_date": end_date,
        "asset_ids": sorted(asset_ids),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
