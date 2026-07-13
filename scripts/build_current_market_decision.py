from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from decision.current_market import (
    build_current_market_decision,
    load_current_market_sources,
)
from decision.current_market.report import write_current_market_decision


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a reproducible current market decision snapshot."
    )
    parser.add_argument("--market-data-as-of")
    parser.add_argument("--decision-date")
    parser.add_argument("--as-of", help="Deprecated alias for --market-data-as-of")
    parser.add_argument(
        "--snapshot-mode",
        choices=("current_decision_with_lagged_market_data", "historical_snapshot"),
        default="current_decision_with_lagged_market_data",
    )
    args = parser.parse_args()
    market_data_as_of = args.market_data_as_of or args.as_of
    if not market_data_as_of:
        parser.error("--market-data-as-of is required")
    if not args.as_of and not args.decision_date:
        parser.error("--decision-date is required")
    if args.as_of:
        warnings.warn(
            "--as-of is deprecated; use --market-data-as-of and --decision-date",
            DeprecationWarning,
            stacklevel=1,
        )
    report = build_current_market_decision(
        market_data_as_of=market_data_as_of,
        decision_date=args.decision_date,
        snapshot_mode=args.snapshot_mode,
        sources=load_current_market_sources(),
    )
    write_current_market_decision(report)
    print(
        json.dumps(
            {
                "available": report.get("available"),
                "status": report.get("status"),
                "decision_date": report.get("decision_date"),
                "market_data_as_of": report.get("market_data_as_of"),
                "governance_state_as_of": report.get("governance_state_as_of"),
                "snapshot_mode": report.get("snapshot_mode"),
                "ready_for_user_review": report.get("ready_for_user_review"),
                "production_actionable": report.get("production_actionable"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
