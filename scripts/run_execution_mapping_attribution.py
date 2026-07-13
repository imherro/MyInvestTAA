import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.execution.data_loader import load_execution_price_dataset
from backtest.execution.dataset_provenance import load_price_dataset_manifest,verify_price_dataset_manifest
from backtest.execution.proposal_attribution import build_proposal_attribution
from backtest.execution.proposal_report import PROPOSAL
from backtest.execution.review_report import ATTRIBUTION,write_review_report
from backtest.research.report import load_research_backtest_report
from engine.asset_registry import load_asset_mappings,load_execution_universe
assets=load_execution_universe();manifest=load_price_dataset_manifest();status=verify_price_dataset_manifest(manifest,assets);provider="tushare" if status["provenance_verified"] else "unverified_local";proposals=json.loads(PROPOSAL.read_text(encoding="utf-8"))["proposals"];report=build_proposal_attribution(load_research_backtest_report(),load_asset_mappings(),proposals,load_execution_price_dataset(assets),assets,provider);report["dataset_provenance"]={**manifest,**status};write_review_report(report,ATTRIBUTION);print({"proposals":len(report["proposal_attributions"]),"provenance_verified":status["provenance_verified"]})
