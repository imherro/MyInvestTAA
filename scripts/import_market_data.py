from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_pipeline import run_import_job


def main() -> int:
    parser = argparse.ArgumentParser(description="Import market data into MyInvestTAA SQLite storage.")
    parser.add_argument("--provider", choices=["mock", "tushare", "baostock"], default="mock")
    parser.add_argument("--assets", required=True, help="Comma-separated asset ids, e.g. 510300,512890")
    parser.add_argument("--database", default=None, help="SQLite database path. Defaults to data/local/myinvest_taa.sqlite")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    asset_ids = [item.strip() for item in args.assets.split(",") if item.strip()]
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
