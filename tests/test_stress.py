import pytest

from backtest.stress import DEFAULT_STRESS_SCENARIOS, StressScenario, build_stress_report
from backtest.taa import run_taa_backtest


def _assets() -> list[dict]:
    return [
        {"id": "510300", "name": "HS300", "anchor_score": 60.0, "start_date": "2018-01-01"},
        {"id": "512760", "name": "Semi", "anchor_score": 55.0, "start_date": "2018-01-01"},
    ]


def _history(start: float, monthly_returns: list[float]) -> list[dict]:
    rows = []
    value = start
    index = 0
    for year in range(2018, 2026):
        for month in range(1, 13):
            value *= 1.0 + monthly_returns[index % len(monthly_returns)]
            rows.append({"date": f"{year}-{month:02d}-28", "close": round(value, 6)})
            index += 1
    return rows


def _histories() -> dict[str, list[dict]]:
    return {
        "510300": _history(1.0, [0.02, -0.01, 0.015, -0.005]),
        "512760": _history(1.0, [0.03, -0.015, 0.02, -0.01]),
    }


def _version_results() -> dict[str, dict]:
    histories = _histories()
    assets = _assets()
    return {
        "V7_STOCK_BREADTH_SELECTION": run_taa_backtest(assets=assets, price_history=histories, score_version="v7"),
        "V11_PRODUCTION_FUSION": run_taa_backtest(assets=assets, price_history=histories, score_version="v11"),
    }


@pytest.mark.parametrize(
    "name",
    [
        "2018_bear",
        "2020_covid",
        "2021_growth_drawdown",
        "2022_bear_market",
        "2024_rotation",
    ],
)
def test_default_stress_scenarios_include_required_windows(name):
    assert name in {scenario.name for scenario in DEFAULT_STRESS_SCENARIOS}


def test_build_stress_report_returns_sections():
    report = build_stress_report(_version_results())

    assert {"version", "scenarios", "rows", "versions", "best_version"} <= set(report)


def test_build_stress_report_records_each_version():
    report = build_stress_report(_version_results())

    assert {"V7_STOCK_BREADTH_SELECTION", "V11_PRODUCTION_FUSION"} <= set(report["versions"])


def test_build_stress_report_records_scenario_count():
    report = build_stress_report(_version_results())

    assert report["versions"]["V11_PRODUCTION_FUSION"]["scenario_count"] == len(DEFAULT_STRESS_SCENARIOS)


def test_build_stress_report_records_pass_rate():
    report = build_stress_report(_version_results())

    assert 0.0 <= report["versions"]["V11_PRODUCTION_FUSION"]["pass_rate"] <= 1.0


def test_build_stress_report_records_stress_score():
    report = build_stress_report(_version_results())

    assert "stress_score" in report["versions"]["V11_PRODUCTION_FUSION"]


def test_build_stress_report_best_version_is_known():
    report = build_stress_report(_version_results())

    assert report["best_version"] in report["versions"]


@pytest.mark.parametrize("field", ["annual_return", "max_drawdown", "recovery_time", "observations", "pass"])
def test_stress_rows_contain_required_fields(field):
    report = build_stress_report(_version_results())

    assert field in report["rows"][0]


@pytest.mark.parametrize("scenario", DEFAULT_STRESS_SCENARIOS)
def test_stress_rows_include_every_default_scenario(scenario):
    report = build_stress_report(_version_results())

    assert scenario.name in {row["scenario"] for row in report["rows"]}


def test_stress_custom_scenario_filters_dates():
    report = build_stress_report(
        _version_results(),
        scenarios=[StressScenario("single_year", "Single Year", "2024-01-01", "2024-12-31")],
    )

    assert report["rows"][0]["scenario"] == "single_year"
    assert report["rows"][0]["observations"] == 12


def test_stress_missing_observations_fail_check():
    report = build_stress_report(
        _version_results(),
        scenarios=[StressScenario("missing", "Missing", "2030-01-01", "2030-12-31")],
    )

    assert report["rows"][0]["pass"] is False
    assert report["versions"]["V11_PRODUCTION_FUSION"]["stress_no_failure"] is False


def test_stress_summary_records_worst_drawdown_and_return():
    report = build_stress_report(_version_results())
    summary = report["versions"]["V11_PRODUCTION_FUSION"]

    assert {"worst_drawdown", "worst_return"} <= set(summary)


def test_stress_report_serializes_scenarios():
    report = build_stress_report(_version_results())

    assert {"name", "label", "start", "end"} <= set(report["scenarios"][0])
