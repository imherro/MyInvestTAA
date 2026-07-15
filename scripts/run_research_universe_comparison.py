from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.research.data_loader import load_research_price_dataset
from backtest.research.universe import load_research_backtest_universe
from backtest.research.universe_comparison import (
    build_research_universe_comparison,
    write_research_universe_comparison,
)
from engine.asset_registry import load_research_universe


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare a research universe before and after one asset is added.")
    parser.add_argument("--added-asset", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    price_data = load_research_price_dataset(load_research_backtest_universe())
    report = build_research_universe_comparison(load_research_universe(), price_data, args.added_asset)
    output = write_research_universe_comparison(report, Path(args.output) if args.output else None)
    print(
        json.dumps(
            {
                "available": report.get("available"),
                "comparison_period": report.get("comparison_period"),
                "metric_deltas": report.get("metric_deltas"),
                "selection_impact": report.get("selection_impact"),
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
