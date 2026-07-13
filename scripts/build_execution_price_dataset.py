from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.execution.data_loader import (
    EXECUTION_PRICE_DIR,
    build_mock_execution_price_dataset,
    fetch_execution_price_dataset_with_errors,
    write_execution_price_dataset,
)
from data_provider.tushare_provider import TushareProvider
from engine.asset_registry import load_execution_universe


def main() -> None:
    parser = argparse.ArgumentParser(description="Build offline ETF qfq execution price cache.")
    parser.add_argument("--provider", choices=["mock", "tushare"], default="mock")
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args()
    assets = load_execution_universe()
    errors: dict[str, str] = {}
    if args.provider == "mock":
        data = build_mock_execution_price_dataset(assets)
    else:
        provider = TushareProvider(return_type="qfq")
        if not provider.provider_status()["available"]:
            raise SystemExit("TUSHARE_TOKEN is required for --provider tushare.")
        data, errors = fetch_execution_price_dataset_with_errors(provider, assets, args.start, args.end)
    write_execution_price_dataset(data)
    manifest = {
        "data_provider": args.provider,
        "return_basis": "qfq",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "start": args.start,
        "end": args.end,
        "asset_count": len(data),
        "available_assets": sum(bool(rows) for rows in data.values()),
        "row_count": sum(len(rows) for rows in data.values()),
        "errors": errors,
        "warning": "ETF cache uses actual ETF trading dates only; no index/ETF history stitching or pre-inception filling.",
    }
    (EXECUTION_PRICE_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({key: manifest[key] for key in ("data_provider", "asset_count", "available_assets", "row_count")})


if __name__ == "__main__":
    main()
