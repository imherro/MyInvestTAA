from __future__ import annotations

from engine.governance.models import StrategyRegistry, StrategyRegistryEntry


PRODUCTION_CANDIDATE = "V3_TREND_RISK_ADJUSTED"
TESTING_VERSION = "V5_RELATIVE_STRENGTH_SELECTION"


def build_strategy_registry(version_rows: list[dict]) -> dict:
    entries = [
        StrategyRegistryEntry(
            version=str(row.get("version")),
            status=_status_for_version(str(row.get("version"))),
            metrics={
                "annual_return": row.get("annual_return", 0.0),
                "max_drawdown": row.get("max_drawdown", 0.0),
                "sharpe": row.get("sharpe", 0.0),
                "calmar": row.get("calmar", 0.0),
            },
        )
        for row in version_rows
    ]
    production = next((entry.version for entry in entries if entry.status == "production_candidate"), None)
    return StrategyRegistry(production_candidate=production, rows=entries).as_dict()


def _status_for_version(version: str) -> str:
    if version == PRODUCTION_CANDIDATE:
        return "production_candidate"
    if version == TESTING_VERSION:
        return "testing"
    return "archive"
