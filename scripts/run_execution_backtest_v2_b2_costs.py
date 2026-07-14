from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.execution.data_loader import load_execution_price_dataset
from backtest.execution.v2.cost_validation import write_cost_outputs
from backtest.execution.v2.costs import load_cost_policy
from backtest.execution.v2.report import COMMITTED as B1_COMMITTED, load_execution_v2_report
from backtest.execution.v2.scenario import run_cost_scenario
from engine.asset_registry import load_execution_universe


def main():
    b1 = load_execution_v2_report()
    if not b1.get("available"):
        raise RuntimeError("verified B1 output set is required")
    b1_marker = json.loads(B1_COMMITTED.read_text(encoding="utf-8"))
    assets = load_execution_universe()
    report, ledger, comparison = run_cost_scenario(
        b1, load_execution_price_dataset(assets), load_cost_policy(),
        b1_output_set_hash=b1_marker["output_set_hash"],
    )
    write_cost_outputs(report, ledger, comparison)
    print(json.dumps({"run_id": report["run_id"], "policy": report["policy"], "cost_attribution": report["cost_attribution"], "comparison": comparison}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
