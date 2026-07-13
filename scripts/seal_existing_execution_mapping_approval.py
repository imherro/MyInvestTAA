from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.execution.approval_integrity import (
    APPROVAL_INTEGRITY_SEAL,
    seal_existing_mapping_approval,
    validate_approval_integrity,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seal the already-applied execution mapping approval."
    )
    parser.add_argument("--expected-package-hash", required=True)
    parser.add_argument("--expected-mapping-after-hash", required=True)
    parser.add_argument("--decision-date", required=True)
    args = parser.parse_args()
    seal = seal_existing_mapping_approval(
        expected_package_hash=args.expected_package_hash,
        expected_mapping_after_hash=args.expected_mapping_after_hash,
        decision_date=args.decision_date,
    )
    print(
        json.dumps(
            {
                "verification_status": seal["verification_status"],
                "seal_hash": hashlib.sha256(
                    APPROVAL_INTEGRITY_SEAL.read_bytes()
                ).hexdigest(),
                "validation": validate_approval_integrity(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
