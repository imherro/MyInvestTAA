import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.execution.mapping_proposal import proposal_collisions
from backtest.execution.proposal_report import PROPOSAL
from backtest.execution.proposal_validation import validate_mapping_review
from backtest.execution.review_report import ATTRIBUTION,REVIEW,write_review_report
from backtest.research.report import load_research_backtest_report
from engine.asset_registry import load_asset_mappings
proposal=json.loads(PROPOSAL.read_text(encoding="utf-8"));attribution=json.loads(ATTRIBUTION.read_text(encoding="utf-8"));semantic=json.loads((ROOT/"data/universe/execution_mapping_semantic_review.json").read_text(encoding="utf-8"));sem={x["research_asset_id"]:x for x in semantic};attr={x["research_asset_id"]:x for x in attribution["proposal_attributions"]};collisions=proposal_collisions(proposal["proposals"],load_research_backtest_report()["monthly_allocations"],load_asset_mappings());violating={asset for row in collisions["proxy_collisions"] if row["violation"] for asset in row["research_asset_ids"]};reviews=[]
for row in proposal["proposals"]:
 decision=validate_mapping_review(attribution["dataset_provenance"],row,attr[row["research_asset_id"]]["marginal_impact"],row["research_asset_id"] in violating,sem[row["research_asset_id"]]["semantic_quality"]);reviews.append({**row,"semantic_review":sem[row["research_asset_id"]],"marginal_attribution":attr[row["research_asset_id"]],"decision":decision})
approved=[x["research_asset_id"] for x in reviews if x["decision"]["result"]=="recommend_manual_approval"];retained=[x["research_asset_id"] for x in reviews if x["decision"]["result"]=="retain_research_only"];rejected=[x["research_asset_id"] for x in reviews if x["decision"]["result"]=="reject_proxy"];report={"available":True,"dataset_provenance":attribution["dataset_provenance"],"proposal_reviews":reviews,"full_overlay_result":attribution["full_overlay"],"proxy_collision_diagnostics":collisions,"drawdown_attribution":attribution["full_overlay"],"decision":{"approved_for_manual_review":approved,"retain_research_only":retained,"rejected":rejected,"ready_for_mapping_update_task":bool(approved) and not retained and not rejected,"reasons":["Formal asset_mapping.json remains unchanged; manual semantic approval is required."]}};write_review_report(report,REVIEW);print(report["decision"])
