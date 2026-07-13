import json
from pathlib import Path
from engine.asset_registry.loader import ROOT
EXECUTION_BACKTEST_REPORT=ROOT/"reports"/"execution_backtest_report.json"
def write_execution_backtest_report(report,path=None):
    target=path or EXECUTION_BACKTEST_REPORT; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return target
def load_execution_backtest_report(path=None):
    target=path or EXECUTION_BACKTEST_REPORT
    if not target.exists(): return {"available":False,"message":"execution backtest report not generated yet"}
    payload=json.loads(target.read_text(encoding="utf-8")); payload["available"]=True; payload["report_path"]=str(target); return payload
