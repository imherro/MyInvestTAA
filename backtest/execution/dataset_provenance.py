from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from backtest.execution.data_loader import EXECUTION_PRICE_DIR, price_file
from engine.asset_registry.loader import ROOT

PRICE_MANIFEST_REPORT = ROOT / "reports" / "execution_price_dataset_manifest.json"
AUDIT_REPORT = ROOT / "reports" / "execution_universe_data_audit_tushare.json"


def build_price_dataset_manifest(assets, cache_manifest_path=None):
    source_path=cache_manifest_path or EXECUTION_PRICE_DIR/"manifest.json"
    source=json.loads(source_path.read_text(encoding="utf-8")) if source_path.exists() else {}
    hashes={asset.asset_id:_sha256(price_file(asset.asset_id)) for asset in assets if price_file(asset.asset_id).exists()}
    return {"provider":source.get("data_provider"),"return_basis":source.get("return_basis"),"audit_report":AUDIT_REPORT.name,"start":source.get("start"),"end":source.get("end"),"asset_count":len(hashes),"generated_at":datetime.now(UTC).isoformat(timespec="seconds"),"dataset_generated_at":source.get("generated_at"),"file_hashes":hashes}


def verify_price_dataset_manifest(manifest, assets, audit=None):
    audit=audit or (json.loads(AUDIT_REPORT.read_text(encoding="utf-8")) if AUDIT_REPORT.exists() else {})
    available={row["asset_id"] for row in audit.get("rows",[]) if row.get("available")}
    errors=[]
    if manifest.get("provider")!="tushare":errors.append("dataset provider is not tushare")
    if manifest.get("return_basis")!="qfq":errors.append("dataset return basis is not qfq")
    for asset in assets:
        path=price_file(asset.asset_id); expected=manifest.get("file_hashes",{}).get(asset.asset_id)
        if not path.exists():errors.append(f"missing price file: {asset.asset_id}")
        elif expected!=_sha256(path):errors.append(f"price file hash mismatch: {asset.asset_id}")
        if asset.asset_id not in available:errors.append(f"audit unavailable: {asset.asset_id}")
    return {"provenance_verified":not errors,"errors":errors}


def write_price_dataset_manifest(report,path=None):
    target=path or PRICE_MANIFEST_REPORT;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return target
def load_price_dataset_manifest(path=None):
    target=path or PRICE_MANIFEST_REPORT
    if not target.exists():return {"available":False,"message":"execution price provenance report not generated yet"}
    value=json.loads(target.read_text(encoding="utf-8"));value["available"]=True;return value
def _sha256(path):return hashlib.sha256(path.read_bytes()).hexdigest()
