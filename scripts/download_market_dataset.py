from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.universe import universe_asset_ids
from data_pipeline import run_import_job
from engine.asset_repository import load_assets


def main() -> int:
    parser = argparse.ArgumentParser(description="Download market dataset into SQLite storage.")
    parser.add_argument("--provider", choices=["mock", "tushare", "baostock"], default="mock")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default="2026-07-08")
    parser.add_argument("--assets", default=None)
    parser.add_argument("--database", default=None)
    args = parser.parse_args()

    if args.assets:
        asset_ids = [item.strip() for item in args.assets.split(",") if item.strip()]
    elif args.provider == "mock":
        asset_ids = [asset["id"] for asset in load_assets()]
    else:
        asset_ids = universe_asset_ids()

    result = run_import_job(
        provider_name=args.provider,
        asset_ids=asset_ids,
        database_path=args.database,
        start=args.start,
        end=args.end,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
