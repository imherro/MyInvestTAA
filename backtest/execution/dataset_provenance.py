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
    files={}
    for asset in assets:
        path=price_file(asset.asset_id)
        if path.exists():files[asset.asset_id]=_file_metadata(path)
    return {"provider":source.get("data_provider"),"return_basis":source.get("return_basis"),"audit_report":AUDIT_REPORT.name,"start":source.get("start"),"end":source.get("end"),"asset_count":len(files),"generated_at":datetime.now(UTC).isoformat(timespec="seconds"),"dataset_generated_at":source.get("generated_at"),"files":files,"file_hashes":{asset_id:metadata["sha256"] for asset_id,metadata in files.items()}}


def verify_price_dataset_manifest(manifest, assets, audit=None):
    audit=audit or (json.loads(AUDIT_REPORT.read_text(encoding="utf-8")) if AUDIT_REPORT.exists() else {})
    audit_rows={row["asset_id"]:row for row in audit.get("rows",[])}
    errors=[]
    if manifest.get("provider")!="tushare":errors.append("dataset provider is not tushare")
    if manifest.get("return_basis")!="qfq":errors.append("dataset return basis is not qfq")
    for asset in assets:
        path=price_file(asset.asset_id); expected=manifest.get("files",{}).get(asset.asset_id,{})
        if not path.exists():errors.append(f"missing price file: {asset.asset_id}")
        else:
            actual=_file_metadata(path)
            for field in ("sha256","row_count","first_date","last_date"):
                if expected.get(field)!=actual.get(field):errors.append(f"price file {field} mismatch: {asset.asset_id}")
        audit_row=audit_rows.get(asset.asset_id)
        if not audit_row or not audit_row.get("available"):errors.append(f"audit unavailable: {asset.asset_id}")
        elif path.exists():
            actual=_file_metadata(path)
            for field in ("row_count","first_date","last_date"):
                if audit_row.get(field)!=actual.get(field):errors.append(f"audit {field} mismatch: {asset.asset_id}")
    return {"provenance_verified":not errors,"errors":errors}


def write_price_dataset_manifest(report,path=None):
    target=path or PRICE_MANIFEST_REPORT;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return target
def load_price_dataset_manifest(path=None):
    target=path or PRICE_MANIFEST_REPORT
    if not target.exists():return {"available":False,"message":"execution price provenance report not generated yet"}
    value=json.loads(target.read_text(encoding="utf-8"));value["available"]=True;return value
def _sha256(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def _file_metadata(path):
    rows=json.loads(path.read_text(encoding="utf-8"))
    return {"sha256":_sha256(path),"row_count":len(rows),"first_date":rows[0]["date"] if rows else None,"last_date":rows[-1]["date"] if rows else None}
