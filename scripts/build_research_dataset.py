from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.universe import universe_asset_ids
from data_pipeline import build_dataset_version
from storage import MarketDataRepository, connect_database


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and store a research dataset version.")
    parser.add_argument("--source", default="tushare")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default="2026-07-08")
    parser.add_argument("--database", default=None)
    args = parser.parse_args()

    version = build_dataset_version(
        source=args.source,
        start_date=args.start,
        end_date=args.end,
        asset_ids=universe_asset_ids(),
    )
    repository = MarketDataRepository(connect_database(args.database))
    repository.save_dataset_version(version)
    print(json.dumps(version.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
