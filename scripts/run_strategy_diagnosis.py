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
from data_pipeline import build_strategy_diagnosis_report
from engine.asset_repository import load_assets
from storage import MarketDataRepository, connect_database


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MyInvestTAA strategy diagnosis.")
    parser.add_argument("--provider", choices=["mock", "tushare", "baostock"], default="tushare")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default="2026-07-08")
    parser.add_argument("--assets", nargs="*", default=None)
    parser.add_argument("--database", default=None)
    parser.add_argument("--output", default=str(ROOT / "reports" / "strategy_diagnosis_report.json"))
    parser.add_argument("--return-type", default="price", choices=["price", "qfq", "hfq", "total_return"])
    parser.add_argument("--skip-import", action="store_true")
    args = parser.parse_args()

    _load_dotenv(ROOT / ".env")
    repository = MarketDataRepository(connect_database(args.database))
    report = build_strategy_diagnosis_report(
        repository,
        provider_name=args.provider,
        start_date=args.start,
        end_date=args.end,
        asset_ids=_resolve_asset_ids(args.provider, args.assets, args.skip_import),
        return_type=args.return_type,
        import_data=not args.skip_import,
        report_path=args.output,
    )
    summary = {
        "provider": report["dataset"]["provider"],
        "assets": report["dataset"]["asset_count"],
        "period": report["dataset"]["period"],
        "best_version": report["versions"]["best_version"],
        "version_rows": report["versions"]["rows"],
        "primary_issue": report["diagnosis"]["summary"][0] if report["diagnosis"]["summary"] else None,
        "report_path": str(Path(args.output)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _resolve_asset_ids(provider_name: str, values: list[str] | None, skip_import: bool) -> list[str] | None:
    if skip_import and values is None:
        return None
    if values:
        return _parse_asset_ids(values)
    if provider_name == "mock":
        return [asset["id"] for asset in load_assets()]
    return universe_asset_ids()


def _parse_asset_ids(values: list[str]) -> list[str]:
    asset_ids: list[str] = []
    for value in values:
        asset_ids.extend(item.strip() for item in value.split(",") if item.strip())
    return asset_ids


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if __name__ == "__main__":
    raise SystemExit(main())
