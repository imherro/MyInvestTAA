from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.research.data_loader import (
    RESEARCH_PRICE_DIR,
    build_mock_research_price_dataset,
    fetch_research_price_dataset,
    load_research_price_dataset,
    write_research_price_dataset,
)
from backtest.research.engine import run_research_backtest
from backtest.research.report import RESEARCH_BACKTEST_REPORT, write_research_backtest_report
from backtest.research.universe import load_research_backtest_universe
from data_provider.tushare_provider import TushareProvider
from engine.asset_registry import load_research_universe


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated Research Backtest MVP.")
    parser.add_argument("--provider", choices=["local", "mock", "tushare"], default="local")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--prices-dir", default=str(RESEARCH_PRICE_DIR))
    parser.add_argument("--output", default=str(RESEARCH_BACKTEST_REPORT))
    args = parser.parse_args()

    _load_dotenv(ROOT / ".env")
    all_assets = load_research_universe()
    assets = load_research_backtest_universe()
    prices_dir = Path(args.prices_dir)
    price_data = _load_or_build_dataset(args.provider, assets, prices_dir, args.start, args.end)
    report = run_research_backtest(all_assets, price_data)
    output = write_research_backtest_report(report, Path(args.output))
    summary = {
        "provider": args.provider,
        "universe_count": report.get("universe_count", 0),
        "available": report.get("available", False),
        "period": report.get("period"),
        "metrics": report.get("metrics"),
        "output": str(output),
        "prices_dir": str(prices_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _load_or_build_dataset(provider_name: str, assets, prices_dir: Path, start: str | None, end: str | None):
    if provider_name == "local":
        return load_research_price_dataset(assets, prices_dir)
    if provider_name == "mock":
        dataset = build_mock_research_price_dataset(assets)
        write_research_price_dataset(dataset, prices_dir)
        return dataset

    provider = TushareProvider()
    if not provider.provider_status()["available"]:
        raise SystemExit("TUSHARE_TOKEN is required for --provider tushare. Use --provider mock or --provider local.")
    dataset = fetch_research_price_dataset(provider, assets, start=start, end=end)
    write_research_price_dataset(dataset, prices_dir)
    return dataset


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
