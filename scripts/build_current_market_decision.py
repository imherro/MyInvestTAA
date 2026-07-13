from __future__ import annotations

import argparse
import json
import sys
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
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args()
    report = build_current_market_decision(
        as_of=args.as_of, sources=load_current_market_sources()
    )
    write_current_market_decision(report)
    print(
        json.dumps(
            {
                "available": report.get("available"),
                "status": report.get("status"),
                "as_of": report.get("as_of"),
                "ready_for_user_review": report.get("ready_for_user_review"),
                "production_actionable": report.get("production_actionable"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
