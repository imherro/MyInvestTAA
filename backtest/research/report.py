from __future__ import annotations

import json
from pathlib import Path

from engine.asset_registry.loader import ROOT


RESEARCH_BACKTEST_REPORT = ROOT / "reports" / "research_backtest_report.json"


def write_research_backtest_report(report: dict, path: Path | None = None) -> Path:
    target = path or RESEARCH_BACKTEST_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_research_backtest_report(path: Path | None = None) -> dict:
    target = path or RESEARCH_BACKTEST_REPORT
    if not target.exists():
        return {
            "available": False,
            "message": "research backtest report not generated yet",
        }
    with target.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    payload["available"] = True
    payload["report_path"] = str(target)
    return payload
