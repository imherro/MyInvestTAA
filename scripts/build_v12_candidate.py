from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.execution.report import load_execution_backtest_report
from backtest.research.candidate import (
    ResearchCandidateSpec,
    build_v12_candidate_report,
    write_v12_candidate_report,
)
from backtest.research.data_loader import load_research_price_dataset
from backtest.research.engine import run_research_backtest
from backtest.research.models import ResearchBacktestConfig
from backtest.research.report import write_research_backtest_report
from backtest.research.universe import load_research_backtest_universe
from backtest.research.universe_comparison import (
    build_research_universe_comparison,
    write_research_universe_comparison,
)
from engine.asset_registry import load_research_universe


def main() -> int:
    spec = ResearchCandidateSpec.load()
    assets = load_research_universe()
    prices = load_research_price_dataset(load_research_backtest_universe())
    research = run_research_backtest(
        assets, prices, config=ResearchBacktestConfig(strategy=spec.strategy_id)
    )
    write_research_backtest_report(research)
    comparison = build_research_universe_comparison(
        assets, prices, spec.added_asset_id
    )
    write_research_universe_comparison(comparison)
    report = build_v12_candidate_report(
        spec, research, comparison, load_execution_backtest_report()
    )
    output = write_v12_candidate_report(report)
    print(
        json.dumps(
            {
                "available": report["available"],
                "strategy_id": report["strategy_id"],
                "period": report["period"],
                "research_metrics": report["research_metrics"],
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
