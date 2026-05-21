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
        """CREATE TABLE IF NOT EXISTS iv_history (
            ticker TEXT,
            date TEXT,
            iv REAL,
            PRIMARY KEY (ticker, date)
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


def upsert_iv_history(ticker: str, date: str, iv: float) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO iv_history VALUES (?, ?, ?)",
            (ticker, date, iv),
        )


def get_iv_history(ticker: str) -> list[tuple[str, float]]:
    """Returns list of (date, iv) sorted by date."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT date, iv FROM iv_history WHERE ticker = ? ORDER BY date",
            (ticker,),
        ).fetchall()
    return rows
