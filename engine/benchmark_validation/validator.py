from __future__ import annotations


def validate_benchmark_report(comparison: dict) -> dict:
    rows = comparison.get("rows", [])
    validations = [validate_benchmark_row(row) for row in rows if row.get("strategy_id") != "MyInvestTAA"]
    return {
        "strategy": "benchmark_suite",
        "weight_check": all(item["weight_check"] for item in validations),
        "return_check": all(item["return_check"] for item in validations),
        "issues": [issue for item in validations for issue in item["issues"]],
        "rows": validations,
        "unit": "percent",
        "notes": [
            "annual_return and max_drawdown are reported in percentage points.",
            "SAA_60_40 cash sleeve uses configured annual cash_return, not a 40 percent annual return.",
        ],
    }


def validate_benchmark_row(row: dict) -> dict:
    issues: list[str] = []
    weights = row.get("weights") or {}
    weight_sum = round(sum(float(value) for value in weights.values()), 4)
    if weights and abs(weight_sum - 100.0) > 0.01:
        issues.append(f"{row['strategy_id']} weights sum to {weight_sum}")
    annual_return = float(row.get("annual_return", 0.0))
    max_drawdown = float(row.get("max_drawdown", 0.0))
    if abs(annual_return) > 100.0:
        issues.append(f"{row['strategy_id']} annual_return magnitude is suspicious: {annual_return}")
    if max_drawdown > 0 or max_drawdown < -100:
        issues.append(f"{row['strategy_id']} max_drawdown is outside expected range: {max_drawdown}")
    return {
        "strategy": row.get("strategy_id"),
        "weight_check": not any("weights" in issue for issue in issues),
        "return_check": not any("annual_return" in issue or "max_drawdown" in issue for issue in issues),
        "weight_sum": weight_sum,
        "annual_return": annual_return,
        "max_drawdown": max_drawdown,
        "issues": issues,
    }
