from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision.v11_current import (
    build_v11_current_allocation_snapshot,
    write_v11_current_allocation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the offline V11 current allocation snapshot."
    )
    parser.add_argument("--market-data-as-of", required=True)
    parser.add_argument(
        "--diagnosis-report",
        default=str(ROOT / "reports" / "strategy_diagnosis_report.json"),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "reports" / "v11_current_allocation.json"),
    )
    args = parser.parse_args()

    diagnosis_path = Path(args.diagnosis_report)
    if not diagnosis_path.exists():
        raise SystemExit(f"strategy diagnosis report not found: {diagnosis_path}")
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    snapshot = build_v11_current_allocation_snapshot(
        diagnosis,
        market_data_as_of=args.market_data_as_of,
        diagnosis_report_path=diagnosis_path,
    )
    output = write_v11_current_allocation(snapshot, Path(args.output))
    print(
        json.dumps(
            {
                "status": snapshot["status"],
                "as_of": snapshot["as_of"],
                "weight_sum_fraction": snapshot["constraint_checks"][
                    "weight_sum_fraction"
                ],
                "source_state_hash": snapshot["source_integrity"][
                    "source_state_hash"
                ],
                "integrity_verified": snapshot["source_integrity"]["verified"],
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if snapshot["available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
