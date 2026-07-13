from __future__ import annotations

import json
from pathlib import Path

from engine.asset_registry.loader import ROOT


CURRENT_MARKET_DECISION_REPORT = ROOT / "reports" / "current_market_decision.json"


def write_current_market_decision(value: dict, path: Path | None = None) -> Path:
    target = path or CURRENT_MARKET_DECISION_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def load_current_market_decision(path: Path | None = None) -> dict:
    target = path or CURRENT_MARKET_DECISION_REPORT
    if not target.exists():
        return {
            "available": False,
            "message": "current market decision report not generated yet",
        }
    value = json.loads(target.read_text(encoding="utf-8"))
    value["available"] = True
    return value
