from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.execution.approval_transaction import recover_transaction


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recover an incomplete execution mapping approval transaction."
    )
    parser.add_argument("--mode", choices=["commit", "rollback"], default="commit")
    args = parser.parse_args()
    print(json.dumps(recover_transaction(mode=args.mode), indent=2))


if __name__ == "__main__":
    main()
