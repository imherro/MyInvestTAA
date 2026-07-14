from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release.models import ReleaseBuildConfig
from release.orchestrator import ReleaseBuildError, build_system_release


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic offline MyInvestTAA release.")
    parser.add_argument("--market-data-as-of", required=True)
    parser.add_argument("--decision-date", required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--provider", required=True, choices=("local",))
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    config = ReleaseBuildConfig(
        market_data_as_of=args.market_data_as_of,
        decision_date=args.decision_date,
        generated_at=args.generated_at,
        provider=args.provider,
        output_dir=args.output_dir,
        commit_sha=_git_sha(),
    )
    try:
        result = build_system_release(config)
    except (ReleaseBuildError, ValueError, OSError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "details": getattr(exc, "errors", [])}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


if __name__ == "__main__":
    raise SystemExit(main())
