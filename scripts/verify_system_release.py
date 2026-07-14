from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release.orchestrator import verify_release_directory


def main() -> int:
    directory = ROOT / "reports" / "release" / "current"
    if not directory.exists():
        print("System release is missing.")
        return 2
    status = verify_release_directory(directory)
    if not status.get("available"):
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 2
    manifest = status.get("manifest", {})
    acceptance = status.get("acceptance", {})
    execution = acceptance.get("execution_integrity", {})
    current = acceptance.get("current_decision_integrity", {})
    summary = {
        "release_id": manifest.get("release_id"),
        "commit_sha": manifest.get("commit_sha"),
        "input_count": len(manifest.get("inputs", [])),
        "artifact_count": len(manifest.get("artifacts", [])),
        "reproducibility_verified": manifest.get("reproducibility", {}).get("verified"),
        "system_acceptance_passed": acceptance.get("system_acceptance_passed"),
        "current_decision_readiness": current.get("verified"),
        "execution_validation_readiness": execution.get("execution_validation_ready"),
        "production_actionable": manifest.get("production_boundary", {}).get("production_actionable"),
        "blocking_errors": acceptance.get("blocking_errors", []) + status.get("errors", []),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if status.get("verified") else 1


if __name__ == "__main__":
    raise SystemExit(main())
