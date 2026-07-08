from __future__ import annotations

from engine.governance.models import StrategyRegistry, StrategyRegistryEntry


PRODUCTION_CANDIDATE = "V3_TREND_RISK_ADJUSTED"
TESTING_VERSIONS = {
    "V5_RELATIVE_STRENGTH_SELECTION",
    "V6_THEME_BREADTH_SELECTION",
    "V7_STOCK_BREADTH_SELECTION",
}


def build_strategy_registry(
    version_rows: list[dict],
    evidence_by_version: dict[str, dict] | None = None,
    promotion_by_version: dict[str, dict] | None = None,
) -> dict:
    evidence_by_version = evidence_by_version or {}
    promotion_by_version = promotion_by_version or {}
    entries = [
        StrategyRegistryEntry(
            version=str(row.get("version")),
            status=_status_for_version(str(row.get("version")), promotion_by_version.get(str(row.get("version")))),
            metrics={
                "annual_return": row.get("annual_return", 0.0),
                "max_drawdown": row.get("max_drawdown", 0.0),
                "sharpe": row.get("sharpe", 0.0),
                "calmar": row.get("calmar", 0.0),
            },
            evidence=evidence_by_version.get(str(row.get("version"))),
            promotion_score=_promotion_value(promotion_by_version.get(str(row.get("version"))), "promotion_score"),
            validation_windows=_promotion_value(promotion_by_version.get(str(row.get("version"))), "validation_windows"),
            approval_status=_promotion_value(promotion_by_version.get(str(row.get("version"))), "approval_status"),
        )
        for row in version_rows
    ]
    production = next((entry.version for entry in entries if entry.status == "candidate"), None)
    return StrategyRegistry(production_candidate=production, rows=entries).as_dict()


def _status_for_version(version: str, promotion: dict | None = None) -> str:
    if promotion and promotion.get("promotion"):
        return "candidate"
    if version == PRODUCTION_CANDIDATE:
        return "candidate"
    if version in TESTING_VERSIONS:
        return "testing"
    return "archive"


def _promotion_value(promotion: dict | None, key: str):
    if not promotion:
        return None
    return promotion.get(key)
