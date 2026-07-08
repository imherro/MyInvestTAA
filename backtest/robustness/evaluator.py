from __future__ import annotations

import random
from statistics import median

from backtest.taa import run_taa_backtest
from backtest.taa.metrics import calculate_taa_metrics


DEFAULT_PARAMETER_GRID = [
    {"target_volatility": target_volatility, "moderate_drawdown": drawdown_threshold}
    for target_volatility in (10.0, 12.0, 15.0)
    for drawdown_threshold in (-5.0, -8.0, -10.0)
]


def build_robustness_report(
    version_results: dict[str, dict],
    assets: list[dict],
    price_history: dict[str, list[dict]],
    stock_price_history: dict[str, list[dict]] | None = None,
    common_kwargs: dict | None = None,
    parameter_grid: list[dict] | None = None,
    bootstrap_samples: int = 200,
) -> dict:
    parameter_sensitivity = run_parameter_sensitivity(
        assets,
        price_history,
        stock_price_history=stock_price_history,
        common_kwargs=common_kwargs,
        parameter_grid=parameter_grid,
    )
    bootstrap = run_bootstrap_by_version(version_results, simulations=bootstrap_samples)
    version_scores = _version_scores(bootstrap, parameter_sensitivity)
    return {
        "version": "robustness_v1",
        "parameter_sensitivity": parameter_sensitivity,
        "bootstrap": bootstrap,
        "version_scores": version_scores,
        "best_version": (
            max(version_scores, key=lambda item: (item["robustness_score"], item["bootstrap"]["median_return"]))["version"]
            if version_scores
            else None
        ),
    }


def run_parameter_sensitivity(
    assets: list[dict],
    price_history: dict[str, list[dict]],
    stock_price_history: dict[str, list[dict]] | None = None,
    common_kwargs: dict | None = None,
    parameter_grid: list[dict] | None = None,
) -> dict:
    grid = parameter_grid or DEFAULT_PARAMETER_GRID
    rows = []
    for params in grid:
        config = _robust_config(params)
        result = run_taa_backtest(
            assets=assets,
            price_history=price_history,
            stock_price_history=stock_price_history,
            score_version="v10",
            max_weight_step=10.0,
            volatility_adjustment=True,
            robust_exposure_config=config,
            **(common_kwargs or {}),
        )
        metrics = result.get("metrics", {})
        row = {
            "target_volatility": config["target_volatility"],
            "drawdown_threshold": config["moderate_drawdown"],
            "deep_drawdown": config["deep_drawdown"],
            "monthly_max_change": config["monthly_max_change"],
            "annual_return": float(metrics.get("annual_return", 0.0)),
            "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
            "sharpe": float(metrics.get("sharpe", 0.0)),
            "calmar": float(metrics.get("calmar", 0.0)),
            "ending_value": float(metrics.get("ending_value", 0.0)),
        }
        row["stable"] = _parameter_row_is_stable(row)
        row["stability_score"] = _parameter_row_score(row)
        rows.append(row)
    stable_count = sum(1 for row in rows if row["stable"])
    return {
        "version": "V10_ROBUST_EXPOSURE",
        "parameter_count": len(rows),
        "stable_parameters": stable_count,
        "pass_rate": round(stable_count / len(rows), 4) if rows else 0.0,
        "stability_score": round(sum(row["stability_score"] for row in rows) / len(rows), 2) if rows else 0.0,
        "rows": rows,
    }


def run_bootstrap_by_version(version_results: dict[str, dict], simulations: int = 200) -> dict:
    rows = []
    versions = {}
    for version, result in version_results.items():
        report = monte_carlo_bootstrap(result, simulations=simulations)
        versions[version] = report
        rows.append({"version": version, **report})
    return {"simulations": simulations, "versions": versions, "rows": rows}


def monte_carlo_bootstrap(backtest_result: dict, simulations: int = 200, seed: int = 7) -> dict:
    if simulations <= 0:
        raise ValueError("simulations must be positive")
    returns = _monthly_returns(backtest_result)
    if not returns:
        return {
            "median_return": 0.0,
            "worst_5_percent": 0.0,
            "best_5_percent": 0.0,
            "median_max_drawdown": 0.0,
            "return_spread": 0.0,
            "pass": False,
        }
    rng = random.Random(seed)
    annual_returns = []
    drawdowns = []
    for _ in range(simulations):
        sampled = [rng.choice(returns) for _ in returns]
        curve = _curve_from_returns(sampled)
        metrics = calculate_taa_metrics(curve, sampled, [])
        annual_returns.append(float(metrics["annual_return"]))
        drawdowns.append(float(metrics["max_drawdown"]))
    annual_returns.sort()
    drawdowns.sort()
    worst = _percentile(annual_returns, 0.05)
    best = _percentile(annual_returns, 0.95)
    median_return = round(median(annual_returns), 4)
    median_drawdown = round(median(drawdowns), 4)
    return {
        "median_return": median_return,
        "worst_5_percent": worst,
        "best_5_percent": best,
        "median_max_drawdown": median_drawdown,
        "return_spread": round(best - worst, 4),
        "pass": worst > -5.0 and median_drawdown > -20.0,
    }


def _robust_config(params: dict) -> dict:
    moderate = float(params.get("moderate_drawdown", params.get("drawdown_threshold", -5.0)))
    return {
        "target_volatility": float(params.get("target_volatility", 12.0)),
        "moderate_drawdown": moderate,
        "deep_drawdown": float(params.get("deep_drawdown", min(-10.0, moderate * 1.5))),
        "monthly_max_change": float(params.get("monthly_max_change", 10.0)),
    }


def _monthly_returns(backtest_result: dict) -> list[float]:
    values = [float(point.get("value", 0.0)) for point in backtest_result.get("equity_curve", [])]
    return [
        current / previous - 1.0
        for previous, current in zip(values, values[1:])
        if previous > 0
    ]


def _curve_from_returns(returns: list[float]) -> list[float]:
    curve = [1.0]
    value = 1.0
    for item in returns:
        value *= 1.0 + item
        curve.append(value)
    return curve


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, int(round((len(values) - 1) * percentile))))
    return round(values[index], 4)


def _parameter_row_is_stable(row: dict) -> bool:
    return (
        float(row.get("annual_return", 0.0)) > 0.0
        and float(row.get("sharpe", 0.0)) > 0.25
        and float(row.get("max_drawdown", 0.0)) >= -15.0
    )


def _parameter_row_score(row: dict) -> float:
    return_score = max(0.0, min(100.0, float(row.get("annual_return", 0.0)) / 5.0 * 100.0))
    sharpe_score = max(0.0, min(100.0, float(row.get("sharpe", 0.0)) / 0.7 * 100.0))
    drawdown_score = max(0.0, min(100.0, (20.0 - abs(float(row.get("max_drawdown", 0.0)))) / 20.0 * 100.0))
    return round(0.35 * return_score + 0.35 * sharpe_score + 0.30 * drawdown_score, 2)


def _version_scores(bootstrap: dict, parameter_sensitivity: dict) -> list[dict]:
    rows = []
    for version, report in bootstrap.get("versions", {}).items():
        score = _bootstrap_score(report)
        if version == "V10_ROBUST_EXPOSURE":
            score = round(0.7 * score + 0.3 * float(parameter_sensitivity.get("stability_score", 0.0)), 2)
        rows.append(
            {
                "version": version,
                "robustness_score": score,
                "pass": bool(report.get("pass")) and score >= 45.0,
                "bootstrap": report,
                "parameter_sensitivity": parameter_sensitivity if version == "V10_ROBUST_EXPOSURE" else {},
            }
        )
    return sorted(rows, key=lambda item: item["robustness_score"], reverse=True)


def _bootstrap_score(report: dict) -> float:
    median_score = max(0.0, min(100.0, float(report.get("median_return", 0.0)) / 5.0 * 100.0))
    worst_score = max(0.0, min(100.0, (float(report.get("worst_5_percent", 0.0)) + 5.0) / 10.0 * 100.0))
    drawdown_score = max(0.0, min(100.0, (20.0 - abs(float(report.get("median_max_drawdown", 0.0)))) / 20.0 * 100.0))
    spread_penalty = min(25.0, max(0.0, float(report.get("return_spread", 0.0)) * 1.5))
    return round(max(0.0, 0.35 * median_score + 0.35 * worst_score + 0.30 * drawdown_score - spread_penalty), 2)
