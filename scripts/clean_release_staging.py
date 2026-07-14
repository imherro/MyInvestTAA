from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release.orchestrator import clean_staging


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean completed release staging directories.")
    parser.add_argument("--include-failed", action="store_true")
    args = parser.parse_args()
    print(json.dumps(clean_staging(keep_failed=not args.include_failed), ensure_ascii=False, indent=2))
