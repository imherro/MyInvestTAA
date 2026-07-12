from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from backtest.research.models import ResearchPrice
from engine.asset_registry.loader import ROOT
from engine.asset_registry.routing import get_asset_history


RESEARCH_PRICE_DIR = ROOT / "data" / "research_prices"


def asset_price_file(asset_id: str, data_dir: Path | None = None) -> Path:
    safe_id = asset_id.replace(".", "_").replace("/", "_")
    return (data_dir or RESEARCH_PRICE_DIR) / f"{safe_id}.json"


def load_research_price_dataset(assets, data_dir: Path | None = None) -> dict[str, list[ResearchPrice]]:
    dataset = {}
    for asset in assets:
        path = asset_price_file(asset.asset_id, data_dir)
        if not path.exists():
            dataset[asset.asset_id] = []
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        dataset[asset.asset_id] = [ResearchPrice.from_mapping(asset.asset_id, row) for row in rows]
    return dataset


def write_research_price_dataset(
    price_data: dict[str, list[ResearchPrice]],
    data_dir: Path | None = None,
) -> list[Path]:
    target_dir = data_dir or RESEARCH_PRICE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for asset_id, rows in sorted(price_data.items()):
        path = asset_price_file(asset_id, target_dir)
        payload = [row.as_dict() for row in rows]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def fetch_research_price_dataset(provider, assets, start: str | None = None, end: str | None = None) -> dict[str, list[ResearchPrice]]:
    dataset = {}
    for asset in assets:
        bars = get_asset_history(provider, asset, start=start, end=end)
        dataset[asset.asset_id] = [
            ResearchPrice(
                asset_id=asset.asset_id,
                date=bar.date,
                close=bar.close,
                return_basis=asset.return_basis,
            )
            for bar in bars
            if bar.close is not None
        ]
    return dataset


def build_mock_research_price_dataset(assets, *, periods: int = 2800) -> dict[str, list[ResearchPrice]]:
    dates = _mock_trading_dates(periods)
    dataset = {}
    for index, asset in enumerate(assets):
        rows = []
        close = 100.0 + index
        monthly_drift = 0.004 + (index % 5) * 0.001
        cycle = 0.0
        for offset, date in enumerate(dates):
            cycle = ((offset % 21) - 10) * 0.00008
            close = max(1.0, close * (1.0 + monthly_drift + cycle))
            rows.append(
                ResearchPrice(
                    asset_id=asset.asset_id,
                    date=date,
                    close=round(close, 6),
                    return_basis=asset.return_basis,
                )
            )
        dataset[asset.asset_id] = rows
    return dataset


def _mock_trading_dates(periods: int) -> list[str]:
    current = date(2016, 1, 4)
    dates = []
    while len(dates) < periods:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates
