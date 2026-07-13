import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.execution.mapping_proposal import build_mapping_proposal
from backtest.execution.proposal_report import PROPOSAL,write_report
from backtest.execution.proxy_report import load_proxy_research_report
report=build_mapping_proposal(load_proxy_research_report());write_report(report,PROPOSAL);print({"proposals":len(report["proposals"]),"output":str(PROPOSAL)})
