import pytest

from backtest.robustness import (
    DEFAULT_PARAMETER_GRID,
    build_robustness_report,
    monte_carlo_bootstrap,
    run_bootstrap_by_version,
    run_parameter_sensitivity,
)
from backtest.taa import run_taa_backtest


def _assets() -> list[dict]:
    return [
        {"id": "510300", "name": "HS300", "anchor_score": 60.0, "start_date": "2020-01-01"},
        {"id": "512760", "name": "Semi", "anchor_score": 55.0, "start_date": "2020-01-01"},
    ]


def _history(start: float, step: float) -> list[dict]:
    rows = []
    value = start
    for year in range(2020, 2026):
        for month in range(1, 13):
            value *= 1.0 + step
            rows.append({"date": f"{year}-{month:02d}-28", "close": round(value, 6)})
    return rows


def _histories() -> dict[str, list[dict]]:
    return {
        "510300": _history(1.0, 0.003),
        "512760": _history(1.0, 0.006),
    }


def _version_results() -> dict[str, dict]:
    histories = _histories()
    assets = _assets()
    return {
        "V6_THEME_BREADTH_SELECTION": run_taa_backtest(assets=assets, price_history=histories, score_version="v6"),
        "V10_ROBUST_EXPOSURE": run_taa_backtest(assets=assets, price_history=histories, score_version="v10"),
    }


def test_default_parameter_grid_covers_target_volatility_values():
    assert {row["target_volatility"] for row in DEFAULT_PARAMETER_GRID} == {10.0, 12.0, 15.0}


def test_default_parameter_grid_covers_drawdown_threshold_values():
    assert {row["moderate_drawdown"] for row in DEFAULT_PARAMETER_GRID} == {-5.0, -8.0, -10.0}


def test_run_parameter_sensitivity_returns_rows():
    report = run_parameter_sensitivity(
        _assets(),
        _histories(),
        parameter_grid=[{"target_volatility": 12.0, "moderate_drawdown": -5.0}],
    )

    assert report["parameter_count"] == 1
    assert report["rows"][0]["target_volatility"] == 12.0


def test_run_parameter_sensitivity_records_stability_score():
    report = run_parameter_sensitivity(
        _assets(),
        _histories(),
        parameter_grid=[{"target_volatility": 12.0, "moderate_drawdown": -5.0}],
    )

    assert "stability_score" in report
    assert "stability_score" in report["rows"][0]


def test_run_parameter_sensitivity_records_deep_drawdown():
    report = run_parameter_sensitivity(
        _assets(),
        _histories(),
        parameter_grid=[{"target_volatility": 12.0, "moderate_drawdown": -8.0}],
    )

    assert report["rows"][0]["deep_drawdown"] == -12.0


def test_monte_carlo_bootstrap_returns_percentiles():
    result = run_taa_backtest(assets=_assets(), price_history=_histories(), score_version="v6")

    report = monte_carlo_bootstrap(result, simulations=20)

    assert {"median_return", "worst_5_percent", "best_5_percent", "median_max_drawdown"} <= set(report)


def test_monte_carlo_bootstrap_is_deterministic():
    result = run_taa_backtest(assets=_assets(), price_history=_histories(), score_version="v6")

    first = monte_carlo_bootstrap(result, simulations=20)
    second = monte_carlo_bootstrap(result, simulations=20)

    assert first == second


def test_monte_carlo_bootstrap_rejects_non_positive_simulations():
    result = run_taa_backtest(assets=_assets(), price_history=_histories(), score_version="v6")

    with pytest.raises(ValueError):
        monte_carlo_bootstrap(result, simulations=0)


def test_monte_carlo_bootstrap_handles_empty_returns():
    report = monte_carlo_bootstrap({"equity_curve": []}, simulations=5)

    assert report["pass"] is False
    assert report["median_return"] == 0.0


def test_run_bootstrap_by_version_returns_versions():
    report = run_bootstrap_by_version(_version_results(), simulations=10)

    assert {"V6_THEME_BREADTH_SELECTION", "V10_ROBUST_EXPOSURE"} <= set(report["versions"])


def test_run_bootstrap_by_version_records_rows():
    report = run_bootstrap_by_version(_version_results(), simulations=10)

    assert len(report["rows"]) == 2
    assert "version" in report["rows"][0]


def test_build_robustness_report_returns_sections():
    report = build_robustness_report(
        _version_results(),
        _assets(),
        _histories(),
        parameter_grid=[{"target_volatility": 12.0, "moderate_drawdown": -5.0}],
        bootstrap_samples=10,
    )

    assert {"parameter_sensitivity", "bootstrap", "version_scores", "best_version"} <= set(report)


def test_build_robustness_report_scores_v10():
    report = build_robustness_report(
        _version_results(),
        _assets(),
        _histories(),
        parameter_grid=[{"target_volatility": 12.0, "moderate_drawdown": -5.0}],
        bootstrap_samples=10,
    )

    assert any(row["version"] == "V10_ROBUST_EXPOSURE" for row in report["version_scores"])


def test_build_robustness_report_sorts_scores_descending():
    report = build_robustness_report(
        _version_results(),
        _assets(),
        _histories(),
        parameter_grid=[{"target_volatility": 12.0, "moderate_drawdown": -5.0}],
        bootstrap_samples=10,
    )
    scores = [row["robustness_score"] for row in report["version_scores"]]

    assert scores == sorted(scores, reverse=True)


def test_build_robustness_report_attaches_parameter_sensitivity_to_v10_only():
    report = build_robustness_report(
        _version_results(),
        _assets(),
        _histories(),
        parameter_grid=[{"target_volatility": 12.0, "moderate_drawdown": -5.0}],
        bootstrap_samples=10,
    )
    v10 = next(row for row in report["version_scores"] if row["version"] == "V10_ROBUST_EXPOSURE")
    v6 = next(row for row in report["version_scores"] if row["version"] == "V6_THEME_BREADTH_SELECTION")

    assert v10["parameter_sensitivity"]
    assert v6["parameter_sensitivity"] == {}


def test_build_robustness_report_records_best_version_from_scores():
    report = build_robustness_report(
        _version_results(),
        _assets(),
        _histories(),
        parameter_grid=[{"target_volatility": 12.0, "moderate_drawdown": -5.0}],
        bootstrap_samples=10,
    )

    assert report["best_version"] in {row["version"] for row in report["version_scores"]}
