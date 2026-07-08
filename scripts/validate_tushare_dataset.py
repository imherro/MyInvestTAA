from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.universe import universe_asset_ids
from data_pipeline import build_validated_performance_report
from engine.asset_repository import load_assets
from storage import MarketDataRepository, connect_database


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Tushare-backed MyInvestTAA dataset.")
    parser.add_argument("--provider", choices=["mock", "tushare", "baostock"], default="tushare")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default="2026-07-08")
    parser.add_argument("--assets", nargs="*", default=None)
    parser.add_argument("--database", default=None)
    args = parser.parse_args()

    _load_dotenv(ROOT / ".env")
    if args.assets:
        asset_ids = _parse_asset_ids(args.assets)
    elif args.provider == "mock":
        asset_ids = [asset["id"] for asset in load_assets()]
    else:
        asset_ids = universe_asset_ids()

    repository = MarketDataRepository(connect_database(args.database))
    report = build_validated_performance_report(
        repository,
        provider_name=args.provider,
        start_date=args.start,
        end_date=args.end,
        asset_ids=asset_ids,
    )
    summary = {
        "provider": args.provider,
        "assets": report["dataset"]["imported_asset_count"],
        "rows": report["dataset"]["price_rows"],
        "quality_score": report["dataset"]["quality_score"],
        "dataset_id": report["dataset"]["dataset_version"]["dataset_id"],
        "annual_return": report["performance"]["annual_return"],
        "max_drawdown": report["performance"]["max_drawdown"],
        "performance_attribution": report["attribution"]["performance"]["top_contributors"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_asset_ids(values: list[str]) -> list[str]:
    asset_ids: list[str] = []
    for value in values:
        asset_ids.extend(item.strip() for item in value.split(",") if item.strip())
    return asset_ids


if __name__ == "__main__":
    raise SystemExit(main())
