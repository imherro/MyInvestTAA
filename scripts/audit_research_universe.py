from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_taa.research_data_audit import (
    audit_research_universe,
    write_audit_report,
)
from current_taa.research_universe import load_research_universe


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the V1 research universe")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--provider-check", action="store_true")
    args = parser.parse_args()

    universe = load_research_universe(ROOT / "config" / "research_universe_v1.json")
    source = None
    selected_mode = "offline"
    if args.provider_check:
        from scripts.update_market_data import TushareMarketDataSource, _load_env_file

        _load_env_file(ROOT / ".env")
        source = TushareMarketDataSource()
        selected_mode = "provider_check"
    report = audit_research_universe(
        universe,
        root=ROOT,
        mode=selected_mode,
        source=source,
    )
    output = ROOT / "reports" / "strategy_research" / "universe_audit.json"
    write_audit_report(output, report)
    summary = report["summary"]
    print(
        f"{selected_mode}: A ready={summary['tier_a_ready']} "
        f"blocked={summary['tier_a_blocked']} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
