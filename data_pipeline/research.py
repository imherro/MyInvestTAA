from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from storage import StoredDatasetVersion


def build_dataset_version(
    source: str,
    start_date: str,
    end_date: str,
    asset_ids: list[str],
    created_at: str | None = None,
) -> StoredDatasetVersion:
    if created_at is None:
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
    dataset_id = f"{end_date.replace('-', '')}_{source.upper()}_CN_ETF"
    return StoredDatasetVersion(
        dataset_id=dataset_id,
        source=source,
        created_at=created_at,
        start_date=start_date,
        end_date=end_date,
        asset_count=len(asset_ids),
        checksum=_dataset_checksum(source, start_date, end_date, asset_ids),
    )


def _dataset_checksum(source: str, start_date: str, end_date: str, asset_ids: list[str]) -> str:
    payload = {
        "source": source,
        "start_date": start_date,
        "end_date": end_date,
        "asset_ids": sorted(asset_ids),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
