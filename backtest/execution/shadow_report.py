from __future__ import annotations

import json
from pathlib import Path

from engine.asset_registry.loader import ROOT

SHADOW_PORTFOLIO_REPORT = ROOT / "reports" / "execution_aware_shadow_portfolio.json"


def write_execution_aware_shadow_portfolio(report, path: Path | None = None):
    target = path or SHADOW_PORTFOLIO_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def load_execution_aware_shadow_portfolio(path: Path | None = None):
    target = path or SHADOW_PORTFOLIO_REPORT
    if not target.exists():
        return {
            "available": False,
            "message": "execution-aware shadow portfolio not generated yet",
        }
    report = json.loads(target.read_text(encoding="utf-8"))
    report["available"] = True
    return report
