"""SQLite persistence for raw Elexon data.

Timestamps are stored as UTC ISO strings; everything is loaded into pandas
for analysis since the whole dataset is only a few tens of thousands of rows.
"""

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.elexon import Actual, Forecast

SCHEMA = """
CREATE TABLE IF NOT EXISTS actuals (
    start_time        TEXT PRIMARY KEY,
    settlement_date   TEXT NOT NULL,
    settlement_period INTEGER NOT NULL,
    generation        INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS forecasts (
    publish_time TEXT NOT NULL,
    start_time   TEXT NOT NULL,
    generation   INTEGER NOT NULL,
    PRIMARY KEY (publish_time, start_time)
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save_actuals(conn: sqlite3.Connection, rows: Iterable[Actual]) -> int:
    cur = conn.executemany(
        "INSERT OR REPLACE INTO actuals VALUES (?, ?, ?, ?)",
        (
            (_ts(r.start_time), r.settlement_date.isoformat(), r.settlement_period, r.generation)
            for r in rows
        ),
    )
    return cur.rowcount


def save_forecasts(conn: sqlite3.Connection, rows: Iterable[Forecast]) -> int:
    cur = conn.executemany(
        "INSERT OR REPLACE INTO forecasts VALUES (?, ?, ?)",
        ((_ts(r.publish_time), _ts(r.start_time), r.generation) for r in rows),
    )
    return cur.rowcount


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


def is_populated(conn: sqlite3.Connection) -> bool:
    actuals = conn.execute("SELECT COUNT(*) FROM actuals").fetchone()[0]
    forecasts = conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
    return bool(actuals and forecasts)


def load_actuals(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT start_time, generation FROM actuals ORDER BY start_time", conn)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    return df


def load_forecasts(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT publish_time, start_time, generation FROM forecasts "
        "ORDER BY publish_time, start_time",
        conn,
    )
    df["publish_time"] = pd.to_datetime(df["publish_time"], utc=True)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    return df
