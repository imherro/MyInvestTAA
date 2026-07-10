from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_provider.tushare_provider import TushareProvider
from engine.asset_registry import (
    build_research_data_availability_audit,
    build_research_universe_mock_provider,
    write_research_data_availability_audit,
)
from engine.asset_registry.data_audit import RESEARCH_DATA_AUDIT_REPORT, RESEARCH_TUSHARE_DATA_AUDIT_REPORT


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit MyInvestTAA research universe data availability.")
    parser.add_argument("--provider", choices=["mock", "tushare"], default="mock")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-assets", type=int, default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    _load_dotenv(ROOT / ".env")
    provider = _build_provider(args.provider)
    report = build_research_data_availability_audit(
        provider,
        start=args.start,
        end=args.end,
        max_assets=args.max_assets,
    )
    output = write_research_data_availability_audit(report, _output_path(args.provider, args.output))
    summary = {
        "provider": report["provider"],
        "checked_assets": report["checked_assets"],
        "available_assets": report["available_assets"],
        "unavailable_assets": report["unavailable_assets"],
        "warnings": len(report["warnings"]),
        "errors": len(report["errors"]),
        "output": str(output),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _build_provider(provider_name: str):
    if provider_name == "mock":
        return build_research_universe_mock_provider()
    provider = TushareProvider()
    if not provider.provider_status()["available"]:
        raise SystemExit("TUSHARE_TOKEN is required for --provider tushare. Use --provider mock for local audit.")
    return provider


def _output_path(provider_name: str, output: str | None) -> Path:
    if output:
        return Path(output)
    if provider_name == "tushare":
        return RESEARCH_TUSHARE_DATA_AUDIT_REPORT
    return RESEARCH_DATA_AUDIT_REPORT


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
