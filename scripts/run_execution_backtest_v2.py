from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.execution.data_loader import load_execution_price_dataset
from backtest.execution.report import load_execution_backtest_report
from backtest.execution.v2 import run_execution_backtest_v2, write_execution_v2_outputs
from backtest.execution.v2.calendar import load_trade_calendar
from backtest.execution.v2.investability import load_instrument_metadata
from backtest.research.report import load_research_backtest_report
from engine.asset_registry import load_asset_mappings, load_execution_universe


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline experimental Execution Engine V2 B1.")
    parser.add_argument("--provider", choices=("local",), default="local")
    parser.parse_args()
    assets = load_execution_universe()
    report, timeline, comparison = run_execution_backtest_v2(
        load_research_backtest_report(),
        load_execution_price_dataset(assets),
        load_asset_mappings(),
        assets,
        load_trade_calendar(),
        load_instrument_metadata(),
        v1_report=load_execution_backtest_report(),
        data_provider="verified_local_tushare",
    )
    if not report.get("available"):
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    write_execution_v2_outputs(report, timeline, comparison)
    print(json.dumps({"strategy": report["strategy"], "periods": report["periods"], "metrics_net": report["metrics_net"], "comparison": comparison}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
