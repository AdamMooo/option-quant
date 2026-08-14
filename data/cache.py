"""
Disposable TTL cache. Safe to delete at any time.

Anything that must survive belongs in data/archive.py instead. The `iv_history`
table that used to live here was INSERT OR REPLACE keyed on run date, so a second
run in the same day silently overwrote the first — it was moved to the append-only
archive 2026-08-14.
"""

import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".cache" / "mx_options.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS options_cache (
            ticker TEXT PRIMARY KEY,
            fetched_at REAL,
            json_blob TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS price_cache (
            ticker TEXT PRIMARY KEY,
            fetched_at REAL,
            json_blob TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS macro_cache (
            series_id TEXT PRIMARY KEY,
            fetched_at REAL,
            value REAL
        )"""
    )
    conn.commit()
    return conn


def get_options(ticker: str, ttl: float) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT fetched_at, json_blob FROM options_cache WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    if row and (time.time() - row[0]) < ttl:
        return json.loads(row[1])
    return None


def set_options(ticker: str, data: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO options_cache VALUES (?, ?, ?)",
            (ticker, time.time(), json.dumps(data)),
        )


def get_prices(ticker: str, ttl: float) -> list | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT fetched_at, json_blob FROM price_cache WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    if row and (time.time() - row[0]) < ttl:
        return json.loads(row[1])
    return None


def set_prices(ticker: str, records: list) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO price_cache VALUES (?, ?, ?)",
            (ticker, time.time(), json.dumps(records)),
        )


def get_macro(series_id: str, ttl: float) -> float | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT fetched_at, value FROM macro_cache WHERE series_id = ?",
            (series_id,),
        ).fetchone()
    if row and (time.time() - row[0]) < ttl:
        return row[1]
    return None


def set_macro(series_id: str, value: float) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO macro_cache VALUES (?, ?, ?)",
            (series_id, time.time(), value),
        )


def get_generic(key: str, ttl: float) -> object:
    """General-purpose cache using price_cache table with a prefixed key."""
    return get_prices(f"__generic_{key}", ttl)


def set_generic(key: str, value: object) -> None:
    set_prices(f"__generic_{key}", value)
