import json
from engine.asset_registry.loader import ROOT
PROPOSAL=ROOT/"reports"/"execution_mapping_proposal.json"; COUNTER=ROOT/"reports"/"execution_mapping_counterfactual_report.json"
def write_report(report,path): path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return path
def load_report(path,message):
    if not path.exists():return {"available":False,"message":message}
    value=json.loads(path.read_text(encoding="utf-8"));value["available"]=True;return value
def load_mapping_proposal_report():return load_report(PROPOSAL,"execution mapping proposal report not generated yet")
def load_counterfactual_report():return load_report(COUNTER,"execution mapping counterfactual report not generated yet")
