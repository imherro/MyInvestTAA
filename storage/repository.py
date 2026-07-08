from __future__ import annotations

import json
import sqlite3

from data.models import AssetMetadata, PriceBar
from storage.models import (
    StoredAsset,
    StoredBacktestResult,
    StoredDatasetVersion,
    StoredPrice,
    StoredSignal,
)


class MarketDataRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert_asset(self, asset: AssetMetadata) -> None:
        self.connection.execute(
            """
            INSERT INTO assets (asset_id, name, asset_class, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
              name=excluded.name,
              asset_class=excluded.asset_class,
              source=excluded.source
            """,
            (asset.asset_id, asset.name, asset.asset_class, asset.source),
        )
        self.connection.commit()

    def upsert_assets(self, assets: list[AssetMetadata]) -> int:
        for asset in assets:
            self.upsert_asset(asset)
        return len(assets)

    def list_assets(self) -> list[StoredAsset]:
        rows = self.connection.execute(
            "SELECT asset_id, name, asset_class, source FROM assets ORDER BY asset_id"
        ).fetchall()
        return [StoredAsset(**dict(row)) for row in rows]

    def get_asset(self, asset_id: str) -> StoredAsset | None:
        row = self.connection.execute(
            "SELECT asset_id, name, asset_class, source FROM assets WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        return StoredAsset(**dict(row)) if row else None

    def upsert_prices(self, prices: list[PriceBar]) -> int:
        self.connection.executemany(
            """
            INSERT INTO prices (asset_id, date, close, source, adjust_type)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(asset_id, date) DO UPDATE SET
              close=excluded.close,
              source=excluded.source,
              adjust_type=excluded.adjust_type
            """,
            [
                (price.asset_id, price.date, price.close, price.source, price.adjust_type)
                for price in prices
            ],
        )
        self.connection.commit()
        return len(prices)

    def get_price_history(self, asset_id: str) -> list[StoredPrice]:
        rows = self.connection.execute(
            """
            SELECT asset_id, date, close, source, adjust_type
            FROM prices
            WHERE asset_id = ?
            ORDER BY date
            """,
            (asset_id,),
        ).fetchall()
        return [StoredPrice(**dict(row)) for row in rows]

    def get_all_price_histories(self) -> dict[str, list[dict]]:
        rows = self.connection.execute(
            "SELECT asset_id, date, close, adjust_type FROM prices ORDER BY asset_id, date"
        ).fetchall()
        histories: dict[str, list[dict]] = {}
        for row in rows:
            histories.setdefault(row["asset_id"], []).append(
                {
                    "date": row["date"],
                    "close": row["close"],
                    "adjust_type": row["adjust_type"],
                }
            )
        return histories

    def upsert_signal(self, signal: StoredSignal) -> None:
        self.connection.execute(
            """
            INSERT INTO signals (
              date, asset_id, drawdown_score, recovery_score, anchor_score, opportunity_score, regime
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, asset_id) DO UPDATE SET
              drawdown_score=excluded.drawdown_score,
              recovery_score=excluded.recovery_score,
              anchor_score=excluded.anchor_score,
              opportunity_score=excluded.opportunity_score,
              regime=excluded.regime
            """,
            (
                signal.date,
                signal.asset_id,
                signal.drawdown_score,
                signal.recovery_score,
                signal.anchor_score,
                signal.opportunity_score,
                signal.regime,
            ),
        )
        self.connection.commit()

    def list_signals(self) -> list[StoredSignal]:
        rows = self.connection.execute(
            """
            SELECT date, asset_id, drawdown_score, recovery_score, anchor_score, opportunity_score, regime
            FROM signals
            ORDER BY date, asset_id
            """
        ).fetchall()
        return [StoredSignal(**dict(row)) for row in rows]

    def save_backtest_result(self, result: StoredBacktestResult) -> None:
        self.connection.execute(
            """
            INSERT INTO backtest_results (strategy, period, metrics_json)
            VALUES (?, ?, ?)
            ON CONFLICT(strategy, period) DO UPDATE SET
              metrics_json=excluded.metrics_json
            """,
            (result.strategy, result.period, json.dumps(result.metrics, ensure_ascii=False, sort_keys=True)),
        )
        self.connection.commit()

    def list_backtest_results(self) -> list[StoredBacktestResult]:
        rows = self.connection.execute(
            "SELECT strategy, period, metrics_json FROM backtest_results ORDER BY strategy, period"
        ).fetchall()
        return [
            StoredBacktestResult(
                strategy=row["strategy"],
                period=row["period"],
                metrics=json.loads(row["metrics_json"]),
            )
            for row in rows
        ]

    def save_dataset_version(self, version: StoredDatasetVersion) -> None:
        self.connection.execute(
            """
            INSERT INTO dataset_versions (
              dataset_id, source, created_at, start_date, end_date, asset_count, checksum
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dataset_id) DO UPDATE SET
              source=excluded.source,
              created_at=excluded.created_at,
              start_date=excluded.start_date,
              end_date=excluded.end_date,
              asset_count=excluded.asset_count,
              checksum=excluded.checksum
            """,
            (
                version.dataset_id,
                version.source,
                version.created_at,
                version.start_date,
                version.end_date,
                version.asset_count,
                version.checksum,
            ),
        )
        self.connection.commit()

    def get_dataset_version(self, dataset_id: str) -> StoredDatasetVersion | None:
        row = self.connection.execute(
            """
            SELECT dataset_id, source, created_at, start_date, end_date, asset_count, checksum
            FROM dataset_versions
            WHERE dataset_id = ?
            """,
            (dataset_id,),
        ).fetchone()
        return StoredDatasetVersion(**dict(row)) if row else None

    def list_dataset_versions(self) -> list[StoredDatasetVersion]:
        rows = self.connection.execute(
            """
            SELECT dataset_id, source, created_at, start_date, end_date, asset_count, checksum
            FROM dataset_versions
            ORDER BY created_at DESC, dataset_id
            """
        ).fetchall()
        return [StoredDatasetVersion(**dict(row)) for row in rows]
