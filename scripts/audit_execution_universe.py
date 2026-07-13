from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_provider.tushare_provider import TushareProvider
from engine.asset_registry.execution_data_audit import (
    build_execution_data_availability_audit,
    write_execution_data_availability_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the ETF execution universe with Tushare qfq data.")
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args()
    provider = TushareProvider(return_type="qfq")
    if not provider.provider_status()["available"]:
        raise SystemExit("TUSHARE_TOKEN is required for the execution universe audit.")
    report = build_execution_data_availability_audit(provider, args.start, args.end)
    target = write_execution_data_availability_audit(report)
    print({"report": str(target), "available_assets": report["available_assets"], "checked_assets": report["checked_assets"]})


if __name__ == "__main__":
    main()
