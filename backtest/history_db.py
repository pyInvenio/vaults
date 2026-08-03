"""SQLite storage for Morpho market history.

The database is intentionally dependency-free and tuned for local analytical
reads: WAL mode, batched upserts, and indexes on both market and timestamp.
"""

from __future__ import annotations

import sqlite3
import hashlib
from pathlib import Path

SCHEMA_VERSION = 3

STATE_TABLES = {
    "DAY": "market_states",
    "HOUR": "market_states_hourly",
}


def event_scope_hash(market_ids) -> str:
    encoded = "\n".join(sorted(market_ids)).encode()
    return hashlib.sha256(encoded).hexdigest()


def connect(path: str | Path, read_only: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if read_only:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA temp_store=MEMORY")
        initialize(db)
    db.row_factory = sqlite3.Row
    return db


def initialize(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS markets (
            market_id TEXT PRIMARY KEY,
            collateral_symbol TEXT NOT NULL,
            loan_symbol TEXT NOT NULL,
            lltv REAL NOT NULL,
            tier TEXT NOT NULL,
            whitelisted INTEGER NOT NULL,
            oracle_note TEXT NOT NULL DEFAULT '',
            pt_maturity_days REAL,
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS market_states (
            market_id TEXT NOT NULL REFERENCES markets(market_id),
            timestamp INTEGER NOT NULL,
            supply_assets_usd REAL NOT NULL,
            borrow_assets_usd REAL NOT NULL,
            supply_apy REAL NOT NULL,
            borrow_apy REAL NOT NULL,
            utilization REAL NOT NULL,
            PRIMARY KEY (market_id, timestamp)
        ) WITHOUT ROWID;

        CREATE INDEX IF NOT EXISTS market_states_by_time
            ON market_states(timestamp, market_id);

        CREATE TABLE IF NOT EXISTS market_states_hourly (
            market_id TEXT NOT NULL REFERENCES markets(market_id),
            timestamp INTEGER NOT NULL,
            supply_assets_usd REAL NOT NULL,
            borrow_assets_usd REAL NOT NULL,
            supply_apy REAL NOT NULL,
            borrow_apy REAL NOT NULL,
            utilization REAL NOT NULL,
            PRIMARY KEY (market_id, timestamp)
        ) WITHOUT ROWID;

        CREATE INDEX IF NOT EXISTS market_states_hourly_by_time
            ON market_states_hourly(timestamp, market_id);

        CREATE TABLE IF NOT EXISTS fetch_windows (
            market_id TEXT NOT NULL,
            start_timestamp INTEGER NOT NULL,
            end_timestamp INTEGER NOT NULL,
            interval TEXT NOT NULL,
            points INTEGER NOT NULL,
            fetched_at INTEGER NOT NULL,
            PRIMARY KEY (market_id, start_timestamp, end_timestamp, interval)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS liquidation_events (
            tx_hash TEXT NOT NULL,
            log_index INTEGER NOT NULL,
            market_id TEXT NOT NULL REFERENCES markets(market_id),
            timestamp INTEGER NOT NULL,
            block_number INTEGER NOT NULL,
            repaid_assets_usd REAL NOT NULL,
            bad_debt_assets_usd REAL NOT NULL,
            seized_assets_raw TEXT NOT NULL,
            liquidator TEXT NOT NULL,
            PRIMARY KEY (tx_hash, log_index)
        ) WITHOUT ROWID;

        CREATE INDEX IF NOT EXISTS liquidation_events_by_time
            ON liquidation_events(timestamp, market_id);

        CREATE TABLE IF NOT EXISTS event_fetch_windows (
            scope_hash TEXT NOT NULL,
            start_timestamp INTEGER NOT NULL,
            end_timestamp INTEGER NOT NULL,
            points INTEGER NOT NULL,
            fetched_at INTEGER NOT NULL,
            PRIMARY KEY (scope_hash, start_timestamp, end_timestamp)
        ) WITHOUT ROWID;
        """
    )
    # Additive migration for earlier databases.
    market_columns = {
        row[1] for row in db.execute("PRAGMA table_info(markets)").fetchall()
    }
    if "oracle_note" not in market_columns:
        db.execute(
            "ALTER TABLE markets ADD COLUMN oracle_note TEXT NOT NULL DEFAULT ''"
        )
    if "pt_maturity_days" not in market_columns:
        db.execute("ALTER TABLE markets ADD COLUMN pt_maturity_days REAL")
    db.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    db.commit()


def upsert_market(db: sqlite3.Connection, market) -> None:
    db.execute(
        """
        INSERT INTO markets(
            market_id, collateral_symbol, loan_symbol, lltv, tier, whitelisted,
            oracle_note, pt_maturity_days, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(market_id) DO UPDATE SET
            collateral_symbol=excluded.collateral_symbol,
            loan_symbol=excluded.loan_symbol,
            lltv=excluded.lltv,
            tier=excluded.tier,
            whitelisted=excluded.whitelisted,
            oracle_note=excluded.oracle_note,
            pt_maturity_days=excluded.pt_maturity_days,
            notes=excluded.notes
        """,
        (
            market.unique_key,
            market.collateral_symbol,
            market.loan_symbol,
            market.lltv,
            market.tier.name,
            int(market.whitelisted),
            market.oracle_note,
            market.pt_maturity_days,
            market.notes,
        ),
    )


def upsert_states(
    db: sqlite3.Connection,
    market_id: str,
    rows: list[dict],
    interval: str = "DAY",
) -> None:
    table = STATE_TABLES.get(interval)
    if table is None:
        raise ValueError(f"unsupported state interval: {interval}")
    db.executemany(
        f"""
        INSERT INTO {table}(
            market_id, timestamp, supply_assets_usd, borrow_assets_usd,
            supply_apy, borrow_apy, utilization
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(market_id, timestamp) DO UPDATE SET
            supply_assets_usd=excluded.supply_assets_usd,
            borrow_assets_usd=excluded.borrow_assets_usd,
            supply_apy=excluded.supply_apy,
            borrow_apy=excluded.borrow_apy,
            utilization=excluded.utilization
        """,
        [
            (
                market_id,
                row["timestamp"],
                row["supply_assets_usd"],
                row["borrow_assets_usd"],
                row["supply_apy"],
                row["borrow_apy"],
                row["utilization"],
            )
            for row in rows
        ],
    )


def upsert_liquidations(db: sqlite3.Connection, rows: list[dict]) -> None:
    db.executemany(
        """
        INSERT INTO liquidation_events(
            tx_hash, log_index, market_id, timestamp, block_number,
            repaid_assets_usd, bad_debt_assets_usd, seized_assets_raw, liquidator
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tx_hash, log_index) DO UPDATE SET
            market_id=excluded.market_id,
            timestamp=excluded.timestamp,
            block_number=excluded.block_number,
            repaid_assets_usd=excluded.repaid_assets_usd,
            bad_debt_assets_usd=excluded.bad_debt_assets_usd,
            seized_assets_raw=excluded.seized_assets_raw,
            liquidator=excluded.liquidator
        """,
        [
            (
                row["tx_hash"],
                row["log_index"],
                row["market_id"],
                row["timestamp"],
                row["block_number"],
                row["repaid_assets_usd"],
                row["bad_debt_assets_usd"],
                row["seized_assets_raw"],
                row["liquidator"],
            )
            for row in rows
        ],
    )


def event_window_fetched(
    db: sqlite3.Connection, scope_hash: str, start: int, end: int
) -> bool:
    return (
        db.execute(
            """
        SELECT 1 FROM event_fetch_windows
        WHERE scope_hash=? AND start_timestamp=? AND end_timestamp=?
        """,
            (scope_hash, start, end),
        ).fetchone()
        is not None
    )


def event_window_covered(
    db: sqlite3.Connection, market_ids, start: int, end: int
) -> bool:
    scope_hash = event_scope_hash(market_ids)
    return (
        db.execute(
            """
        SELECT 1 FROM event_fetch_windows
        WHERE scope_hash=? AND start_timestamp<=? AND end_timestamp>=?
        """,
            (scope_hash, start, end),
        ).fetchone()
        is not None
    )


def record_event_window(
    db: sqlite3.Connection,
    scope_hash: str,
    start: int,
    end: int,
    points: int,
    fetched_at: int,
) -> None:
    db.execute(
        """
        INSERT OR REPLACE INTO event_fetch_windows(
            scope_hash, start_timestamp, end_timestamp, points, fetched_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (scope_hash, start, end, points, fetched_at),
    )


def window_fetched(
    db: sqlite3.Connection,
    market_id: str,
    start: int,
    end: int,
    interval: str,
) -> bool:
    row = db.execute(
        """
        SELECT 1 FROM fetch_windows
        WHERE market_id=? AND start_timestamp<=? AND end_timestamp>=? AND interval=?
        """,
        (market_id, start, end, interval),
    ).fetchone()
    return row is not None


def record_window(
    db: sqlite3.Connection,
    market_id: str,
    start: int,
    end: int,
    interval: str,
    points: int,
    fetched_at: int,
) -> None:
    db.execute(
        """
        INSERT OR REPLACE INTO fetch_windows(
            market_id, start_timestamp, end_timestamp, interval, points, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (market_id, start, end, interval, points, fetched_at),
    )


def coverage(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT m.market_id, m.collateral_symbol, COUNT(s.timestamp) AS points,
               MIN(s.timestamp) AS first_timestamp, MAX(s.timestamp) AS last_timestamp,
               SUM(CASE WHEN s.supply_assets_usd <= 0 THEN 1 ELSE 0 END) AS invalid_supply
        FROM markets m
        LEFT JOIN market_states s ON s.market_id = m.market_id
        GROUP BY m.market_id, m.collateral_symbol
        ORDER BY m.collateral_symbol, m.market_id
        """
    ).fetchall()
