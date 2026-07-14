from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release.orchestrator import recover_release


if __name__ == "__main__":
    result = recover_release()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get("recovered") or "valid" in result.get("status", "") else 1)
