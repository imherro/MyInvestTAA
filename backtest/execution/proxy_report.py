from __future__ import annotations
import json
from pathlib import Path
from engine.asset_registry.loader import ROOT
EXECUTION_PROXY_RESEARCH_REPORT=ROOT/"reports"/"execution_proxy_research_report.json"
def write_proxy_research_report(report,path=None):
    target=path or EXECUTION_PROXY_RESEARCH_REPORT;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return target
def load_proxy_research_report(path=None):
    target=path or EXECUTION_PROXY_RESEARCH_REPORT
    if not target.exists():return {"available":False,"message":"execution proxy research report not generated yet"}
    payload=json.loads(target.read_text(encoding="utf-8"));payload["available"]=True;return payload
