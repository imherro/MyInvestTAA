from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.execution.data_loader import (
    EXECUTION_PRICE_DIR,
    build_mock_execution_price_dataset,
    fetch_execution_price_dataset_with_errors,
    load_execution_price_dataset,
    write_execution_price_dataset,
)
from backtest.execution.engine import run_execution_backtest
from backtest.execution.mapping_improvement import build_mapping_improvement_report, write_mapping_improvement_report
from backtest.execution.mapping_application import load_mapping_approval_record, validate_approval_record
from backtest.execution.approval_integrity import load_approval_integrity_seal
from backtest.execution.approval_package import load_mapping_decision_ledger
from backtest.execution.report import write_execution_backtest_report
from backtest.research.report import load_research_backtest_report
from data_provider.tushare_provider import TushareProvider
from engine.asset_registry import build_research_universe_audit, load_asset_mappings, load_execution_universe
from engine.asset_registry.loader import ASSET_MAPPING_FILE


def _local_provider() -> str:
    manifest = EXECUTION_PRICE_DIR / "manifest.json"
    if not manifest.exists():
        return "local"
    return str(json.loads(manifest.read_text(encoding="utf-8")).get("data_provider", "local"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an offline ETF execution proxy backtest.")
    parser.add_argument("--provider", choices=["local", "mock", "tushare"], default="local")
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args()
    assets = load_execution_universe()
    provider_name = args.provider
    if args.provider == "local":
        data = load_execution_price_dataset(assets)
        provider_name = _local_provider()
    elif args.provider == "mock":
        data = build_mock_execution_price_dataset(assets)
    else:
        provider = TushareProvider(return_type="qfq")
        if not provider.provider_status()["available"]:
            raise SystemExit("TUSHARE_TOKEN is required for --provider tushare.")
        data, errors = fetch_execution_price_dataset_with_errors(provider, assets, args.start, args.end)
        write_execution_price_dataset(data)
        if errors:
            print({"data_fetch_errors": sorted(errors)})
    report = run_execution_backtest(
        load_research_backtest_report(), data, load_asset_mappings(), assets, data_provider=provider_name
    )
    approval_record = load_mapping_approval_record()
    approval_status = (
        validate_approval_record(approval_record)
        if approval_record.get("available")
        else {"approval_record_verified": False, "errors": ["approval record missing"]}
    )
    approval_seal = load_approval_integrity_seal()
    report["mapping_registry_version"] = hashlib.sha256(ASSET_MAPPING_FILE.read_bytes()).hexdigest()
    report["approved_mapping_records"] = approval_seal.get("approved_mappings", [])
    report["approval_record_verification"] = approval_status
    report["asset_registry_validation"] = build_research_universe_audit()
    write_execution_backtest_report(report)
    write_mapping_improvement_report(
        build_mapping_improvement_report(report, load_mapping_decision_ledger())
    )
    print({"available": report.get("available"), "provider": provider_name, "period": report.get("period"), "metrics": report.get("metrics")})


if __name__ == "__main__":
    main()
