from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "local" / "myinvest_taa.sqlite"


def connect_database(path: str | Path | None = None) -> sqlite3.Connection:
    database_path = DEFAULT_DB_PATH if path is None else path
    if database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    initialize_database(connection)
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            asset_class TEXT NOT NULL,
            source TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prices (
            asset_id TEXT NOT NULL,
            date TEXT NOT NULL,
            close REAL NOT NULL,
            source TEXT NOT NULL,
            adjust_type TEXT NOT NULL DEFAULT 'none',
            return_type TEXT NOT NULL DEFAULT 'price',
            PRIMARY KEY (asset_id, date)
        );

        CREATE TABLE IF NOT EXISTS signals (
            date TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            drawdown_score REAL NOT NULL,
            recovery_score REAL NOT NULL,
            anchor_score REAL NOT NULL,
            opportunity_score REAL NOT NULL,
            regime TEXT NOT NULL,
            PRIMARY KEY (date, asset_id)
        );

        CREATE TABLE IF NOT EXISTS backtest_results (
            strategy TEXT NOT NULL,
            period TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            PRIMARY KEY (strategy, period)
        );

        CREATE TABLE IF NOT EXISTS dataset_versions (
            dataset_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            asset_count INTEGER NOT NULL,
            checksum TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS experiments (
            experiment_id TEXT PRIMARY KEY,
            config_hash TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            result_json TEXT NOT NULL
        );
        """
    )
    _ensure_column(connection, "prices", "adjust_type", "TEXT NOT NULL DEFAULT 'none'")
    _ensure_column(connection, "prices", "return_type", "TEXT NOT NULL DEFAULT 'price'")
    connection.commit()


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
