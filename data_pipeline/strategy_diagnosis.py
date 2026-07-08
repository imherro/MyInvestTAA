from __future__ import annotations

import json
from pathlib import Path

from backtest.benchmark import compare_strategies
from backtest.taa import run_taa_backtest
from config import load_research_config
from data.universe import universe_asset_ids
from data_pipeline.full_validation import _research_assets
from data_pipeline.importer import build_provider, import_market_data
from engine.asset_repository import load_assets
from engine.benchmark_validation import validate_benchmark_report
from engine.diagnosis import analyze_regime_effects, compare_strategy_versions, decompose_vs_static
from engine.governance import build_strategy_registry
from engine.performance_attribution import analyze_regime_contribution
from engine.performance_attribution.v3 import decompose_excess_return_v3
from engine.regime.v3 import detect_market_regime_v3
from engine.selection import build_selection_analysis, compare_selection_attribution
from storage import MarketDataRepository


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIAGNOSIS_PATH = ROOT / "reports" / "strategy_diagnosis_report.json"


def build_strategy_diagnosis_report(
    repository: MarketDataRepository,
    provider_name: str = "mock",
    start_date: str = "2016-01-01",
    end_date: str = "2026-07-08",
    asset_ids: list[str] | None = None,
    return_type: str = "price",
    import_data: bool = True,
    report_path: str | Path | None = DEFAULT_DIAGNOSIS_PATH,
) -> dict:
    config = load_research_config()
    backtest_config = config["backtest"]
    if asset_ids is None:
        asset_ids = _default_asset_ids(provider_name, repository)
    if import_data or not repository.get_all_price_histories():
        provider = build_provider(provider_name, return_type=return_type)
        import_market_data(
            provider,
            repository,
            asset_ids,
            start=start_date,
            end=end_date,
            min_quality_score=float(config["universe"].get("min_quality_score", 50.0)),
        )

    histories = _month_end_histories(repository.get_all_price_histories())
    assets = _research_assets(asset_ids, repository)
    common_kwargs = {
        "assets": assets,
        "price_history": histories,
        "transaction_cost": float(backtest_config.get("transaction_cost", 0.0)),
        "cash_return": float(backtest_config.get("cash_return", 0.0)),
        "slippage": float(backtest_config.get("slippage", 0.0)),
        "expense_ratio": float(backtest_config.get("expense_ratio", 0.0)),
    }
    variants = {
        "V1_CURRENT": run_taa_backtest(**common_kwargs),
        "V2_REGIME_SMOOTHING": run_taa_backtest(**common_kwargs, max_weight_step=10.0),
        "V3_TREND_RISK_ADJUSTED": run_taa_backtest(
            **common_kwargs,
            score_version="v4",
            max_weight_step=10.0,
            volatility_adjustment=True,
        ),
        "V4_REGIME_EXPOSURE_FLOOR": run_taa_backtest(
            **common_kwargs,
            score_version="v4",
            max_weight_step=10.0,
            volatility_adjustment=True,
            equity_floor_by_regime={"bull": 70.0, "neutral": 40.0, "bear_recovery": 50.0},
        ),
        "V5_RELATIVE_STRENGTH_SELECTION": run_taa_backtest(
            **common_kwargs,
            score_version="v5",
            max_weight_step=10.0,
            volatility_adjustment=True,
        ),
        "V6_THEME_BREADTH_SELECTION": run_taa_backtest(
            **common_kwargs,
            score_version="v6",
            max_weight_step=10.0,
            volatility_adjustment=True,
        ),
    }
    benchmark = compare_strategies(**common_kwargs)
    static_row = benchmark["strategies"].get("SAA_60_40")
    benchmark_validation = validate_benchmark_report(benchmark)
    regime_analysis = analyze_regime_effects(variants["V1_CURRENT"])
    decomposition = decompose_vs_static(variants["V1_CURRENT"], static_row)
    attribution_v3 = decompose_excess_return_v3(variants["V4_REGIME_EXPOSURE_FLOOR"], static_row)
    attribution_v5 = decompose_excess_return_v3(variants["V5_RELATIVE_STRENGTH_SELECTION"], static_row)
    attribution_v6 = decompose_excess_return_v3(variants["V6_THEME_BREADTH_SELECTION"], static_row)
    selection_attribution = compare_selection_attribution(
        decompose_excess_return_v3(variants["V3_TREND_RISK_ADJUSTED"], static_row),
        attribution_v5,
    )
    version_comparison = compare_strategy_versions(variants)
    selection_attribution_v2 = compare_selection_attribution(
        attribution_v5,
        attribution_v6,
        baseline="V5_RELATIVE_STRENGTH_SELECTION",
        candidate="V6_THEME_BREADTH_SELECTION",
    )
    strategy_registry = build_strategy_registry(
        version_comparison["rows"],
        evidence_by_version={
            "V6_THEME_BREADTH_SELECTION": {
                "periods": 3,
                "improvement": selection_attribution_v2["selection"]["improved"],
            }
        },
    )
    regime_contribution = analyze_regime_contribution(variants["V1_CURRENT"])
    regime_v3 = detect_market_regime_v3(histories.get("510300", []), breadth=_estimate_breadth(histories))
    selection_analysis = build_selection_analysis(variants["V6_THEME_BREADTH_SELECTION"])
    report = {
        "dataset": {
            "provider": provider_name,
            "period": {"start": start_date, "end": end_date},
            "asset_count": len(asset_ids),
            "return_type": return_type,
            "frequency": "month_end",
        },
        "diagnosis": {
            "summary": _diagnosis_summary(regime_analysis, decomposition, regime_contribution),
            "regime_analysis": regime_analysis,
            "decomposition": decomposition,
            "regime_contribution": regime_contribution,
            "attribution_v3": attribution_v3,
            "attribution_v5": attribution_v5,
            "attribution_v6": attribution_v6,
            "selection_attribution": selection_attribution,
            "selection_attribution_v2": selection_attribution_v2,
            "selection_analysis": selection_analysis,
            "regime_v3": regime_v3,
        },
        "versions": version_comparison,
        "strategy_registry": strategy_registry,
        "benchmark": {
            "static": static_row,
            "rows": benchmark["rows"],
            "validation": benchmark_validation,
        },
        "recommendations": [
            "Use exposure smoothing to reduce abrupt bull_caution de-risking.",
            "Add trend confirmation so drawdown signals do not buy weakening assets too early.",
            "Use volatility adjustment to avoid oversized high-volatility positions.",
            "Prioritize total-return data before declaring investment performance conclusions.",
            "Use relative strength as a selection layer before promoting V5 from testing.",
            "Validate theme momentum and breadth stability before promoting V6.",
        ],
    }
    if report_path is not None:
        _write_report(Path(report_path), report)
    return report


def _default_asset_ids(provider_name: str, repository: MarketDataRepository) -> list[str]:
    histories = repository.get_all_price_histories()
    if histories:
        return sorted(histories)
    if provider_name == "mock":
        return [asset["id"] for asset in load_assets()]
    return universe_asset_ids()


def _month_end_histories(histories: dict[str, list[dict]]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for asset_id, history in histories.items():
        by_month: dict[str, dict] = {}
        for row in sorted(history, key=lambda item: str(item["date"])):
            by_month[str(row["date"])[:7]] = row
        result[asset_id] = [by_month[key] for key in sorted(by_month)]
    return result


def _estimate_breadth(histories: dict[str, list[dict]]) -> float | None:
    positives = 0
    observations = 0
    for history in histories.values():
        if len(history) < 2:
            continue
        previous = float(history[-2]["close"])
        current = float(history[-1]["close"])
        if previous <= 0:
            continue
        positives += 1 if current > previous else 0
        observations += 1
    if observations == 0:
        return None
    return round(positives / observations, 4)


def _diagnosis_summary(regime_analysis: dict, decomposition: dict, regime_contribution: dict) -> list[dict]:
    sources = []
    worst_regime = regime_analysis.get("worst_regime")
    if worst_regime:
        sources.append(
            {
                "source": f"{worst_regime} allocation drag",
                "severity": "high",
                "evidence": f"Worst regime allocation effect: {worst_regime}",
            }
        )
    if decomposition.get("return_gap", 0.0) < 0:
        sources.append(
            {
                "source": "static allocation return gap",
                "severity": "high",
                "evidence": f"Return gap vs {decomposition['benchmark']}: {decomposition['return_gap']}",
            }
        )
    contribution = regime_contribution.get("contribution", {})
    if contribution.get("bull_caution", 0.0) < 0:
        sources.append(
            {
                "source": "bull_caution de-risking",
                "severity": "medium",
                "evidence": f"bull_caution contribution: {contribution['bull_caution']}",
            }
        )
    return sources


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
