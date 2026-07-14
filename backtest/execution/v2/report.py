from __future__ import annotations

import json
from pathlib import Path

from engine.asset_registry.loader import ROOT


REPORT = ROOT / "reports" / "execution_backtest_v2_report.json"
TIMELINE = ROOT / "reports" / "execution_investability_timeline.json"
COMPARISON = ROOT / "reports" / "execution_v1_v2_comparison.json"


def write_execution_v2_outputs(report: dict, timeline: dict, comparison: dict) -> None:
    for path, value in ((REPORT, report), (TIMELINE, timeline), (COMPARISON, comparison)):
        path.parent.mkdir(parents=True, exist_ok=True)
        indent = None if path == TIMELINE else 2
        path.write_text(json.dumps(value, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8")


def load_execution_v2_report(path: Path | None = None) -> dict:
    target = path or REPORT
    if not target.exists():
        return {"available": False, "message": "execution V2 report not generated yet"}
    value = json.loads(target.read_text(encoding="utf-8"))
    value["available"] = True
    return value
