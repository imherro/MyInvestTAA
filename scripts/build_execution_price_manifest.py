import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.execution.dataset_provenance import build_price_dataset_manifest,verify_price_dataset_manifest,write_price_dataset_manifest
from engine.asset_registry import load_execution_universe
assets=load_execution_universe();report=build_price_dataset_manifest(assets);report.update(verify_price_dataset_manifest(report,assets));write_price_dataset_manifest(report);print({"provenance_verified":report["provenance_verified"],"asset_count":report["asset_count"]})
