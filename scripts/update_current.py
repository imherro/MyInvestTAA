from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_taa.pipeline import run_current_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the CURRENT_TAA five-report product pipeline")
    parser.add_argument("--shadow-start-date", help="Fixed Shadow activation date (YYYY-MM-DD)")
    args = parser.parse_args()
    try:
        reports = run_current_pipeline(root=ROOT, shadow_start_date=args.shadow_start_date)
    except Exception as exc:
        print(f"CURRENT_TAA update failed: {exc}", file=sys.stderr)
        return 1
    research = reports["research.json"]
    allocation = reports["allocation.json"]
    shadow = reports["shadow.json"]
    print(
        "CURRENT_TAA updated: "
        f"research={research['period']['start']}..{research['period']['end']} "
        f"decision={allocation['decision_date']} shadow={shadow['start_date']}..{shadow['end_date']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
