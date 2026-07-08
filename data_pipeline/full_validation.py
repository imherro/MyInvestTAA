from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from backtest.benchmark import compare_strategies
from backtest.taa import run_taa_backtest
from config import build_config_hash, load_research_config
from data.universe import load_china_etf_universe, universe_asset_ids
from data_pipeline.importer import build_provider, import_market_data
from data_pipeline.research import build_dataset_version
from engine.asset_repository import load_assets
from engine.attribution import analyze_attribution
from engine.data_quality import build_quality_summary
from engine.performance_attribution import (
    analyze_performance_contribution,
    analyze_regime_contribution,
)
from storage import MarketDataRepository, StoredExperiment


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = ROOT / "reports" / "full_validation_report.json"


def build_full_validation_report(
    repository: MarketDataRepository,
    provider_name: str = "mock",
    start_date: str = "2016-01-01",
    end_date: str = "2026-07-08",
    asset_ids: list[str] | None = None,
    return_type: str | None = None,
    config: dict | None = None,
    report_path: str | Path | None = DEFAULT_REPORT_PATH,
) -> dict:
    research_config = config or load_research_config()
    backtest_config = research_config.get("backtest", {})
    universe_config = research_config.get("universe", {})
    if return_type is None:
        return_type = str(backtest_config.get("return_type", "price"))
    if asset_ids is None:
        asset_ids = _default_asset_ids(provider_name)

    provider = build_provider(provider_name, return_type=return_type)
    import_summary = import_market_data(
        provider,
        repository,
        asset_ids,
        start=start_date,
        end=end_date,
        min_quality_score=float(universe_config.get("min_quality_score", 50.0)),
    )
    histories = repository.get_all_price_histories()
    research_assets = _research_assets(asset_ids, repository)
    quality = build_quality_summary(histories)
    config_hash = build_config_hash(research_config)
    version = build_dataset_version(
        source=provider_name,
        start_date=start_date,
        end_date=end_date,
        asset_ids=asset_ids,
    )
    repository.save_dataset_version(version)

    backtest = run_taa_backtest(
        assets=research_assets,
        price_history=histories,
        rebalance_frequency=str(backtest_config.get("rebalance_frequency", "monthly")),
        transaction_cost=float(backtest_config.get("transaction_cost", 0.0)),
        cash_return=float(backtest_config.get("cash_return", 0.0)),
        slippage=float(backtest_config.get("slippage", 0.0)),
        expense_ratio=float(backtest_config.get("expense_ratio", 0.0)),
    )
    benchmark = compare_strategies(
        assets=research_assets,
        price_history=histories,
        transaction_cost=float(backtest_config.get("transaction_cost", 0.0)),
        cash_return=float(backtest_config.get("cash_return", 0.0)),
        slippage=float(backtest_config.get("slippage", 0.0)),
        expense_ratio=float(backtest_config.get("expense_ratio", 0.0)),
    )
    performance_attribution = analyze_performance_contribution(
        backtest_result=backtest,
        price_history=histories,
    )
    regime_attribution = analyze_regime_contribution(backtest)
    decision_attribution = analyze_attribution(backtest)

    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    experiment_id = f"{version.dataset_id}_{config_hash[:8]}"
    report = {
        "experiment": {
            "experiment_id": experiment_id,
            "config_hash": config_hash,
            "created_at": created_at,
        },
        "dataset": {
            "provider": provider_name,
            "dataset_id": version.dataset_id,
            "asset_count": import_summary["imported_assets"],
            "assets": asset_ids,
            "period": {"start": start_date, "end": end_date},
            "rows": import_summary["imported_prices"],
            "quality_score": quality["average_score"],
            "return_type": return_type,
        },
        "config": research_config,
        "performance": {
            "strategy": backtest["strategy"],
            "period": backtest["period"],
            **backtest["metrics"],
        },
        "benchmark": {
            "rows": benchmark["rows"],
            "alpha": benchmark["alpha"],
            "HS300": benchmark["strategies"].get("HS300_BUY_HOLD"),
            "SAA_CLASSIC": benchmark["strategies"].get("SAA_CLASSIC"),
        },
        "attribution": {
            "decision": decision_attribution,
            "asset_contribution": performance_attribution["asset_contribution"],
            "top_contributors": performance_attribution["top_contributors"],
            "regime_contribution": regime_attribution,
        },
        "reproducibility": {
            "dataset_id": version.dataset_id,
            "config_hash": config_hash,
            "experiment_id": experiment_id,
        },
    }
    repository.save_experiment(
        StoredExperiment(
            experiment_id=experiment_id,
            config_hash=config_hash,
            dataset_id=version.dataset_id,
            created_at=created_at,
            result=report,
        )
    )
    if report_path is not None:
        _write_report(Path(report_path), report)
    return report


def _default_asset_ids(provider_name: str) -> list[str]:
    if provider_name == "mock":
        return [asset["id"] for asset in load_assets()]
    return universe_asset_ids()


def _research_assets(asset_ids: list[str], repository: MarketDataRepository) -> list[dict]:
    sample_by_id = {asset["id"]: asset for asset in load_assets()}
    universe_by_id = {asset["id"]: asset for asset in load_china_etf_universe()}
    stored_by_id = {asset.asset_id: asset for asset in repository.list_assets()}
    assets: list[dict] = []
    for asset_id in asset_ids:
        if asset_id in sample_by_id:
            asset = dict(sample_by_id[asset_id])
            universe = universe_by_id.get(asset_id, {})
            asset.setdefault("start_date", universe.get("start_date"))
            asset.setdefault("end_date", universe.get("end_date"))
            assets.append(asset)
            continue
        universe = universe_by_id.get(asset_id)
        stored = stored_by_id.get(asset_id)
        if universe is None and stored is None:
            continue
        assets.append(_asset_from_metadata(asset_id, universe or {}, stored))
    return assets


def _asset_from_metadata(asset_id: str, universe: dict, stored) -> dict:
    asset_class = str(universe.get("asset_class") or getattr(stored, "asset_class", "equity"))
    category = str(universe.get("category") or "unknown")
    anchor_score = _default_anchor_score(asset_class, category)
    return {
        "id": asset_id,
        "name": str(universe.get("name") or getattr(stored, "name", asset_id)),
        "type": "etf",
        "asset_class": asset_class,
        "style": str(universe.get("style") or category),
        "category": category,
        "market": "CN",
        "benchmark": "",
        "risk_level": _default_risk_level(asset_class, category),
        "anchor_score": anchor_score,
        "anchor_reason": "Universe-derived anchor profile for full validation.",
        "placeholder_score": anchor_score,
        "strategic_weight_pct": 0,
        "current_weight_pct": 0,
        "max_drawdown": _default_max_drawdown(asset_class),
        "reference_max_drawdown_pct": _default_max_drawdown(asset_class),
        "prices": [],
        "start_date": universe.get("start_date"),
        "end_date": universe.get("end_date"),
    }


def _default_anchor_score(asset_class: str, category: str) -> float:
    if asset_class == "bond":
        return 80.0
    if asset_class == "commodity":
        return 70.0
    if category == "style":
        return 68.0
    if category == "broad_base":
        return 60.0
    if asset_class == "commodity_equity":
        return 45.0
    return 50.0


def _default_risk_level(asset_class: str, category: str) -> str:
    if asset_class == "bond":
        return "low"
    if asset_class == "commodity":
        return "medium"
    if category == "sector":
        return "high"
    return "medium"


def _default_max_drawdown(asset_class: str) -> float:
    if asset_class == "bond":
        return -8.0
    if asset_class == "commodity":
        return -25.0
    if asset_class == "commodity_equity":
        return -55.0
    return -50.0


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
