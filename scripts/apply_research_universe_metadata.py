from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.asset_registry.loader import RESEARCH_UNIVERSE_FILE
from engine.asset_registry.return_basis_review import MANUAL_REVIEW_ASSET_IDS


MANUAL_REVIEW_NOTE = "创业板R口径待人工确认；暂不进入主TAA配置"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply approved research universe metadata suggestions.")
    parser.add_argument("--suggestions", default=str(ROOT / "reports" / "research_universe_metadata_suggestions.json"))
    parser.add_argument("--registry", default=str(RESEARCH_UNIVERSE_FILE))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--freeze-manual-review-assets", action="store_true")
    args = parser.parse_args()

    summary = apply_research_universe_metadata(
        suggestions_path=Path(args.suggestions),
        registry_path=Path(args.registry),
        write=args.write,
        freeze_manual_review_assets=args.freeze_manual_review_assets,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def apply_research_universe_metadata(
    *,
    suggestions_path: Path,
    registry_path: Path,
    write: bool = False,
    freeze_manual_review_assets: bool = False,
) -> dict:
    suggestions = _read_json_object(suggestions_path)
    registry = _read_json_list(registry_path)
    suggestion_by_id = {
        str(row["asset_id"]): row
        for row in suggestions.get("suggestions", [])
        if row.get("asset_id") and row.get("data_start_date") and row.get("investable_start_date")
    }

    changed_assets = []
    applied_count = 0
    frozen_count = 0
    for asset in registry:
        asset_id = str(asset["asset_id"])
        suggestion = suggestion_by_id.get(asset_id)
        changes: dict[str, object] = {}
        if suggestion:
            for field in ("data_start_date", "investable_start_date"):
                new_value = suggestion[field]
                if asset.get(field) != new_value:
                    changes[field] = {"from": asset.get(field), "to": new_value}
                    asset[field] = new_value
            if changes:
                applied_count += 1

        if freeze_manual_review_assets and asset_id in MANUAL_REVIEW_ASSET_IDS:
            if asset.get("eligible_for_allocation") is not False:
                changes["eligible_for_allocation"] = {"from": asset.get("eligible_for_allocation"), "to": False}
                asset["eligible_for_allocation"] = False
                frozen_count += 1
            if asset.get("notes") != MANUAL_REVIEW_NOTE:
                changes["notes"] = {"from": asset.get("notes"), "to": MANUAL_REVIEW_NOTE}
                asset["notes"] = MANUAL_REVIEW_NOTE

        if changes:
            changed_assets.append({"asset_id": asset_id, "changes": changes})

    if write:
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "mode": "write" if write else "dry_run",
        "registry": str(registry_path),
        "suggestions": str(suggestions_path),
        "suggestion_count": len(suggestion_by_id),
        "applied_metadata_assets": applied_count,
        "frozen_manual_review_assets": frozen_count,
        "changed_asset_count": len(changed_assets),
        "changed_assets": changed_assets,
    }


def _read_json_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _read_json_list(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
