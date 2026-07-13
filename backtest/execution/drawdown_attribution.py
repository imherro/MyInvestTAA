from __future__ import annotations

from datetime import date


def drawdown_window(report: dict) -> dict:
    curve = report.get("equity_curve", [])
    if not curve:
        return {
            "max_drawdown": 0.0,
            "peak_date": None,
            "trough_date": None,
            "recovery_date": None,
            "decline_days": 0,
            "underwater_days": 0,
            "recovery_days": 0,
            "recovered": False,
        }

    peak_value = float(curve[0]["value"])
    peak_date = curve[0]["date"]
    best = (0.0, peak_date, peak_date, peak_value)
    for row in curve:
        value = float(row["value"])
        if value > peak_value:
            peak_value = value
            peak_date = row["date"]
        drawdown = value / peak_value - 1
        if drawdown < best[0]:
            best = (drawdown, peak_date, row["date"], peak_value)

    recovery_date = next(
        (
            row["date"]
            for row in curve
            if row["date"] > best[2] and float(row["value"]) >= best[3]
        ),
        None,
    )
    report_end = curve[-1]["date"]
    underwater_end = recovery_date or report_end
    recovery_end = recovery_date or report_end
    return {
        "max_drawdown": round(best[0], 6),
        "peak_date": best[1],
        "trough_date": best[2],
        "recovery_date": recovery_date,
        "decline_days": _days(best[1], best[2]),
        "underwater_days": _days(best[1], underwater_end),
        "recovery_days": _days(best[2], recovery_end),
        "recovered": recovery_date is not None,
    }


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days
