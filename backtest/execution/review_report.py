import json
from engine.asset_registry.loader import ROOT
ATTRIBUTION=ROOT/"reports"/"execution_mapping_drawdown_attribution.json";REVIEW=ROOT/"reports"/"execution_mapping_review_report.json"
def write_review_report(value,path):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return path
def _load(path,message):
    if not path.exists():return {"available":False,"message":message}
    value=json.loads(path.read_text(encoding="utf-8"));value["available"]=True;return value
def load_mapping_attribution_report():return _load(ATTRIBUTION,"execution mapping attribution report not generated yet")
def load_mapping_review_report():return _load(REVIEW,"execution mapping review report not generated yet")
