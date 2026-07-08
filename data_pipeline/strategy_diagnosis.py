from __future__ import annotations

import json
from pathlib import Path

from backtest.benchmark import compare_strategies
from backtest.taa import run_taa_backtest
from backtest.walk_forward import run_walk_forward_validation
from config import load_research_config
from data.universe import universe_asset_ids
from data_pipeline.full_validation import _research_assets
from data_pipeline.importer import build_provider, import_market_data
from data_pipeline.normalizer import price_bars_to_history
from engine.adaptive import adaptive_weight_snapshot
from engine.asset_repository import load_assets
from engine.benchmark_validation import validate_benchmark_report
from engine.diagnosis import analyze_regime_effects, compare_strategy_versions, decompose_vs_static
from engine.governance import build_promotion_report, build_strategy_registry, build_strategy_selection_report
from engine.performance_attribution import analyze_regime_contribution
from engine.performance_attribution.v3 import decompose_excess_return_v3
from engine.regime.v3 import detect_market_regime_v3
from engine.selection import (
    build_selection_analysis,
    compare_adaptive_selection_attribution,
    compare_selection_attribution,
)
from engine.stock_breadth import rank_stock_breadth, stock_breadth_coverage, stock_theme_universe, theme_for_stock
from engine.theme import theme_for_asset
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
    stock_histories, stock_breadth_meta = _load_stock_breadth_histories(
        provider_name,
        histories,
        start_date=start_date,
        end_date=end_date,
    )
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
        "V7_STOCK_BREADTH_SELECTION": run_taa_backtest(
            **common_kwargs,
            score_version="v7",
            max_weight_step=10.0,
            volatility_adjustment=True,
            stock_price_history=stock_histories,
        ),
        "V8_ADAPTIVE_SELECTION": run_taa_backtest(
            **common_kwargs,
            score_version="v8",
            max_weight_step=10.0,
            volatility_adjustment=True,
            stock_price_history=stock_histories,
        ),
        "V9_EXPOSURE_OPTIMIZED": run_taa_backtest(
            **common_kwargs,
            score_version="v9",
            max_weight_step=10.0,
            volatility_adjustment=True,
            stock_price_history=stock_histories,
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
    attribution_v7 = decompose_excess_return_v3(variants["V7_STOCK_BREADTH_SELECTION"], static_row)
    attribution_v8 = decompose_excess_return_v3(variants["V8_ADAPTIVE_SELECTION"], static_row)
    attribution_v9 = decompose_excess_return_v3(variants["V9_EXPOSURE_OPTIMIZED"], static_row)
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
    selection_attribution_v3 = compare_selection_attribution(
        attribution_v6,
        attribution_v7,
        baseline="V6_THEME_BREADTH_SELECTION",
        candidate="V7_STOCK_BREADTH_SELECTION",
    )
    adaptive_selection_attribution = compare_adaptive_selection_attribution(
        attribution_v7,
        attribution_v8,
    )
    exposure_selection_attribution = compare_adaptive_selection_attribution(
        attribution_v8,
        attribution_v9,
        baseline="V8_ADAPTIVE_SELECTION",
        candidate="V9_EXPOSURE_OPTIMIZED",
    )
    walk_forward = run_walk_forward_validation(
        assets=assets,
        price_history=histories,
        stock_price_history=stock_histories,
        common_kwargs={
            "transaction_cost": common_kwargs["transaction_cost"],
            "cash_return": common_kwargs["cash_return"],
            "slippage": common_kwargs["slippage"],
            "expense_ratio": common_kwargs["expense_ratio"],
        },
    )
    promotion = build_promotion_report(version_comparison["rows"], walk_forward)
    strategy_selection = build_strategy_selection_report(version_comparison["rows"], walk_forward)
    promotion_by_version = {row["version"]: row for row in promotion["rows"]}
    stock_breadth_rows = rank_stock_breadth(stock_histories, source=stock_breadth_meta["source"])
    strategy_registry = build_strategy_registry(
        version_comparison["rows"],
        evidence_by_version={
            "V6_THEME_BREADTH_SELECTION": {
                "periods": 3,
                "improvement": selection_attribution_v2["selection"]["improved"],
            },
            "V7_STOCK_BREADTH_SELECTION": {
                "periods": walk_forward.get("windows", 0),
                "improvement": selection_attribution_v3["selection"]["improved"],
                "stock_breadth_coverage": stock_breadth_coverage(stock_breadth_rows)["coverage_ratio"],
            },
            "V8_ADAPTIVE_SELECTION": {
                "periods": walk_forward.get("windows", 0),
                "improvement": adaptive_selection_attribution["improved"],
                "stock_breadth_coverage": stock_breadth_coverage(stock_breadth_rows)["coverage_ratio"],
            },
            "V9_EXPOSURE_OPTIMIZED": {
                "periods": walk_forward.get("windows", 0),
                "improvement": exposure_selection_attribution["improved"],
                "stock_breadth_coverage": stock_breadth_coverage(stock_breadth_rows)["coverage_ratio"],
            }
        },
        promotion_by_version=promotion_by_version,
    )
    regime_contribution = analyze_regime_contribution(variants["V1_CURRENT"])
    regime_v3 = detect_market_regime_v3(histories.get("510300", []), breadth=_estimate_breadth(histories))
    selection_analysis = build_selection_analysis(variants["V9_EXPOSURE_OPTIMIZED"])
    adaptive_selection = _adaptive_selection_report(variants["V9_EXPOSURE_OPTIMIZED"])
    exposure_analysis = _exposure_analysis_report(variants["V9_EXPOSURE_OPTIMIZED"])
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
            "attribution_v7": attribution_v7,
            "attribution_v8": attribution_v8,
            "attribution_v9": attribution_v9,
            "selection_attribution": selection_attribution,
            "selection_attribution_v2": selection_attribution_v2,
            "selection_attribution_v3": selection_attribution_v3,
            "adaptive_selection_attribution": adaptive_selection_attribution,
            "exposure_selection_attribution": exposure_selection_attribution,
            "selection_analysis": selection_analysis,
            "adaptive_selection": adaptive_selection,
            "exposure_analysis": exposure_analysis,
            "stock_breadth": {
                **stock_breadth_meta,
                "coverage": stock_breadth_coverage(stock_breadth_rows),
                "rows": stock_breadth_rows,
            },
            "walk_forward": walk_forward,
            "promotion": promotion,
            "strategy_selection": strategy_selection,
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
            "Use stock breadth and walk-forward promotion rules before promoting V7.",
            "Use adaptive factor weights to improve V8 risk-return stability before promotion.",
            "Use exposure optimization and strategy selection scoring before promoting V9.",
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


def _load_stock_breadth_histories(
    provider_name: str,
    etf_histories: dict[str, list[dict]],
    start_date: str,
    end_date: str,
) -> tuple[dict[str, list[dict]], dict]:
    if provider_name == "mock":
        histories = _mock_stock_histories(etf_histories)
        return histories, {
            "source": "mock_stock_constituents",
            "mode": "mock",
            "requested": len(stock_theme_universe()),
            "loaded": len(histories),
            "failures": [],
        }
    if provider_name != "tushare":
        return {}, {
            "source": "unavailable_stock_daily",
            "mode": provider_name,
            "requested": len(stock_theme_universe()),
            "loaded": 0,
            "failures": [f"{provider_name} stock breadth adapter is not configured"],
        }

    provider = build_provider("tushare", return_type="price")
    histories: dict[str, list[dict]] = {}
    failures: list[str] = []
    for stock_id in stock_theme_universe():
        try:
            bars = provider.get_stock_price_history(stock_id, start=start_date, end=end_date)
        except Exception as exc:  # pragma: no cover - live provider failures depend on local credentials.
            failures.append(f"{stock_id}: {exc}")
            continue
        history = price_bars_to_history(bars)
        if history:
            histories[stock_id] = history
        else:
            failures.append(f"{stock_id}: empty history")
    return histories, {
        "source": "tushare_stock_daily",
        "mode": "live",
        "requested": len(stock_theme_universe()),
        "loaded": len(histories),
        "failures": failures[:20],
    }


def _mock_stock_histories(etf_histories: dict[str, list[dict]]) -> dict[str, list[dict]]:
    representative_by_theme: dict[str, list[dict]] = {}
    for asset_id, history in etf_histories.items():
        representative_by_theme.setdefault(theme_for_asset(asset_id), history)
    histories: dict[str, list[dict]] = {}
    for index, stock_id in enumerate(stock_theme_universe()):
        theme = _mock_stock_theme(stock_id)
        base_history = representative_by_theme.get(theme) or next(iter(etf_histories.values()), [])
        if not base_history:
            continue
        scale = 1.0 + ((index % 7) - 3) * 0.01
        histories[stock_id] = [
            {
                **row,
                "close": round(float(row["close"]) * scale * (1.0 + ((offset % 5) - 2) * 0.001), 6),
            }
            for offset, row in enumerate(base_history)
        ]
    return histories


def _mock_stock_theme(stock_id: str) -> str:
    return theme_for_stock(stock_id)


def _adaptive_selection_report(backtest_result: dict) -> dict:
    states = [
        state for state in backtest_result.get("states", [])
        if state.get("signals", {}).get("scores")
    ]
    if not states:
        return {"version": "v8", "rows": []}
    latest = states[-1]
    regime_state = latest.get("regime", {}).get("state", "neutral")
    weights = latest.get("signals", {}).get("adaptive_factor_weights") or adaptive_weight_snapshot(regime_state)
    rows = []
    for item in latest.get("signals", {}).get("scores", [])[:10]:
        rows.append(
            {
                "asset": item.get("id"),
                "name": item.get("name"),
                "theme": item.get("theme"),
                "opportunity_score": item.get("opportunity_score", 0.0),
                "adaptive_regime": item.get("adaptive_regime", regime_state),
                "adaptive_reason": item.get("adaptive_reason", ""),
                "factor_weights": item.get("adaptive_factor_weights", weights),
            }
        )
    return {
        "version": backtest_result.get("assumptions", {}).get("score_version", "v8"),
        "date": latest.get("date"),
        "regime": regime_state,
        "factor_weights": weights,
        "rows": rows,
    }


def _exposure_analysis_report(backtest_result: dict) -> dict:
    states = [
        state for state in backtest_result.get("states", [])
        if state.get("signals", {}).get("exposure_decision")
    ]
    if not states:
        return {"version": backtest_result.get("assumptions", {}).get("score_version"), "rows": []}
    rows = [
        {
            "date": state.get("date"),
            "regime": state.get("regime", {}).get("state"),
            **state.get("signals", {}).get("exposure_decision", {}),
        }
        for state in states[-12:]
    ]
    latest = rows[-1]
    return {
        "version": backtest_result.get("assumptions", {}).get("score_version"),
        "date": latest.get("date"),
        "current": latest,
        "rows": rows,
    }


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
