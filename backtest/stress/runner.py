from __future__ import annotations

from datetime import date

from backtest.stress.models import StressScenario, StressScenarioResult
from backtest.stress.scenarios import DEFAULT_STRESS_SCENARIOS
from backtest.taa.metrics import calculate_taa_metrics


def build_stress_report(
    version_results: dict[str, dict],
    scenarios: list[StressScenario] | None = None,
) -> dict:
    scenario_list = scenarios or DEFAULT_STRESS_SCENARIOS
    rows: list[dict] = []
    versions: dict[str, dict] = {}
    for version, result in version_results.items():
        version_rows = [
            _scenario_result(version, result, scenario).as_dict()
            for scenario in scenario_list
        ]
        rows.extend(version_rows)
        versions[version] = _version_summary(version, version_rows)
    best_version = (
        max(
            versions.values(),
            key=lambda item: (
                item["stress_no_failure"],
                item["stress_score"],
                item["worst_drawdown"],
                item["worst_return"],
            ),
        )["version"]
        if versions
        else None
    )
    return {
        "version": "stress_v1",
        "scenarios": [scenario.as_dict() for scenario in scenario_list],
        "rows": rows,
        "versions": versions,
        "best_version": best_version,
    }


def _scenario_result(version: str, result: dict, scenario: StressScenario) -> StressScenarioResult:
    states = [
        state
        for state in result.get("states", [])
        if _in_window(str(state.get("date")), scenario.start, scenario.end)
    ]
    values = [float(state.get("portfolio_value", 0.0)) for state in states]
    if len(values) < 2:
        metrics = calculate_taa_metrics(values or [1.0], [], [])
    else:
        returns = [
            current / previous - 1.0
            for previous, current in zip(values, values[1:])
            if previous > 0
        ]
        metrics = calculate_taa_metrics(values, returns, [])
    annual_return = float(metrics.get("annual_return", 0.0))
    max_drawdown = float(metrics.get("max_drawdown", 0.0))
    pass_check = (
        len(values) >= 2
        and annual_return >= scenario.min_annual_return
        and max_drawdown >= scenario.max_drawdown_floor
    )
    return StressScenarioResult(
        version=version,
        scenario=scenario.name,
        label=scenario.label,
        start=scenario.start,
        end=scenario.end,
        observations=len(values),
        annual_return=annual_return,
        max_drawdown=max_drawdown,
        sharpe=float(metrics.get("sharpe", 0.0)),
        calmar=float(metrics.get("calmar", 0.0)),
        ending_value=float(metrics.get("ending_value", 0.0)),
        recovery_time=_recovery_time(values),
        pass_check=pass_check,
    )


def _version_summary(version: str, rows: list[dict]) -> dict:
    scenario_count = len(rows)
    passed = sum(1 for row in rows if row.get("pass"))
    observed_rows = [row for row in rows if int(row.get("observations", 0)) >= 2]
    recovery_times = [
        int(row["recovery_time"])
        for row in observed_rows
        if row.get("recovery_time") is not None
    ]
    worst_drawdown = min((float(row.get("max_drawdown", 0.0)) for row in observed_rows), default=0.0)
    worst_return = min((float(row.get("annual_return", 0.0)) for row in observed_rows), default=0.0)
    stress_score = _stress_score(rows)
    return {
        "version": version,
        "scenario_count": scenario_count,
        "passed_scenarios": passed,
        "pass_rate": round(passed / scenario_count, 4) if scenario_count else 0.0,
        "stress_no_failure": bool(scenario_count and passed == scenario_count),
        "stress_score": stress_score,
        "worst_drawdown": round(worst_drawdown, 4),
        "worst_return": round(worst_return, 4),
        "avg_recovery_time": (
            round(sum(recovery_times) / len(recovery_times), 2)
            if recovery_times
            else None
        ),
        "rows": rows,
    }


def _stress_score(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    scores = []
    for row in rows:
        if int(row.get("observations", 0)) < 2:
            scores.append(0.0)
            continue
        return_score = max(0.0, min(100.0, (float(row.get("annual_return", 0.0)) + 20.0) / 30.0 * 100.0))
        drawdown_score = max(0.0, min(100.0, (20.0 - abs(float(row.get("max_drawdown", 0.0)))) / 20.0 * 100.0))
        recovery = row.get("recovery_time")
        recovery_score = 70.0 if recovery is None else max(0.0, min(100.0, (18.0 - float(recovery)) / 18.0 * 100.0))
        scenario_score = 0.45 * return_score + 0.40 * drawdown_score + 0.15 * recovery_score
        if not row.get("pass"):
            scenario_score *= 0.5
        scores.append(scenario_score)
    return round(sum(scores) / len(scores), 2)


def _recovery_time(values: list[float]) -> int | None:
    if len(values) < 2:
        return None
    peak = values[0]
    peak_index = 0
    trough_peak_index = 0
    trough_index = 0
    worst_drawdown = 0.0
    for index, value in enumerate(values):
        if value > peak:
            peak = value
            peak_index = index
        drawdown = value / peak - 1.0 if peak > 0 else 0.0
        if drawdown < worst_drawdown:
            worst_drawdown = drawdown
            trough_peak_index = peak_index
            trough_index = index
    recovery_target = values[trough_peak_index]
    for index in range(trough_index + 1, len(values)):
        if values[index] >= recovery_target:
            return index - trough_peak_index
    return None


def _in_window(value: str, start: str, end: str) -> bool:
    current = date.fromisoformat(value)
    return date.fromisoformat(start) <= current <= date.fromisoformat(end)
