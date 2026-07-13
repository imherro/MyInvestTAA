from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.execution.mapping_application import apply_human_approved_mapping


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply the explicitly human-approved 931743 execution mapping."
    )
    parser.add_argument("--explicit-approval", required=True, choices=["approved"])
    parser.add_argument("--expected-package-hash", required=True)
    parser.add_argument("--expected-mapping-hash", required=True)
    parser.add_argument("--decision-date", required=True)
    args = parser.parse_args()
    record = apply_human_approved_mapping(
        explicit_approval=args.explicit_approval,
        expected_package_hash=args.expected_package_hash,
        expected_mapping_hash=args.expected_mapping_hash,
        decision_date=args.decision_date,
    )
    print(
        json.dumps(
            {
                "research_asset_id": record["research_asset_id"],
                "approved_proxy": record["approved_proxy"],
                "expected_package_hash_input": record["expected_package_hash_input"],
                "actual_package_hash": record["actual_package_hash"],
                "mapping_before_hash": record["mapping_before_hash"],
                "mapping_after_hash": record["mapping_after_hash"],
                "production_approved": record["production_approved"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
