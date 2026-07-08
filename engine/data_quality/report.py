from __future__ import annotations

from engine.asset_repository import load_price_histories
from engine.data_quality.models import DataQualityReport
from engine.data_quality.validator import validate_price_history


def build_quality_summary(
    price_histories: dict[str, list[dict]] | None = None,
) -> dict:
    if price_histories is None:
        price_histories = load_price_histories()

    reports = [
        validate_price_history(asset_id, history)
        for asset_id, history in sorted(price_histories.items())
    ]
    average_score = (
        round(sum(report.score for report in reports) / len(reports), 2)
        if reports
        else 0.0
    )
    issue_count = sum(
        report.duplicate_rows + report.invalid_prices + report.abnormal_jumps
        for report in reports
    )
    return {
        "source": "mock",
        "asset_count": len(reports),
        "average_score": average_score,
        "issue_count": issue_count,
        "reports": [report.as_dict() for report in reports],
    }
