from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.asset_registry import (
    build_metadata_suggestions,
    build_return_basis_review,
    load_research_data_availability_report,
    write_metadata_suggestions,
    write_return_basis_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate metadata suggestions and return-basis review from a research universe audit report."
    )
    parser.add_argument("--audit-report", default=str(ROOT / "reports" / "research_universe_data_audit_tushare.json"))
    parser.add_argument("--metadata-output", default=str(ROOT / "reports" / "research_universe_metadata_suggestions.json"))
    parser.add_argument("--return-basis-output", default=str(ROOT / "reports" / "research_universe_return_basis_review.json"))
    args = parser.parse_args()

    audit_report = load_research_data_availability_report(Path(args.audit_report))
    if not audit_report.get("available"):
        raise SystemExit(str(audit_report["message"]))

    metadata_report = build_metadata_suggestions(audit_report)
    return_basis_report = build_return_basis_review(audit_report)
    metadata_output = write_metadata_suggestions(metadata_report, Path(args.metadata_output))
    return_basis_output = write_return_basis_review(return_basis_report, Path(args.return_basis_output))

    summary = {
        "audit_report": args.audit_report,
        "suggestion_count": metadata_report["suggestion_count"],
        "blocked_asset_count": metadata_report["blocked_asset_count"],
        "registered_total_return_available": len(return_basis_report["registered_total_return_available"]),
        "basis_confirmed_total_return": len(return_basis_report["basis_confirmed_total_return"]),
        "provider_metadata_mismatch": len(return_basis_report["provider_metadata_mismatch"]),
        "needs_manual_review": len(return_basis_report["needs_manual_review"]),
        "unavailable_total_return": len(return_basis_report["unavailable_total_return"]),
        "price_index_monitor_assets": len(return_basis_report["price_index_monitor_assets"]),
        "metadata_output": str(metadata_output),
        "return_basis_output": str(return_basis_output),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
