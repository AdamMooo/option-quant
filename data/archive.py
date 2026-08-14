"""
Append-only point-in-time archive of option chain snapshots.

This is the repo's most important asset and its rules are deliberately rigid:

  1. Rows are INSERTed. Never UPDATEd, never DELETEd, never INSERT OR REPLACE.
     SQLite triggers enforce this — an accidental UPDATE raises, it does not
     silently clobber. The predecessor `iv_history` table used INSERT OR REPLACE
     keyed on run date, so running the tool twice in a day overwrote the morning's
     observation with the afternoon's and nobody could tell.

  2. Observations are stored; derived quantities are not. DTE, VRP, moneyness and
     rank are all recomputed on read. If the definition of "ATM" changes later,
     history must not silently change with it.

  3. Every row carries both when we fetched it (`captured_at`) and what the
     exchange said the quote time was (`source_ts`). Those are different facts and
     conflating them is how lookahead gets in.

Separate database file from `.cache/` on purpose: the cache is disposable and
TTL-overwritten, this is not. Wiping `.cache/` must never touch the archive.

Units: contract IV is stored as a percentage (22.4 = 22.4%). CBOE delivers
per-contract IV as a decimal and `iv30` as a percentage; normalizing to one unit
at the boundary is not interpretation, but it is a conversion — hence this note.
"""

import datetime
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "archive" / "chains.db"

_APPEND_ONLY_TABLES = ("snapshots", "underlying", "contracts")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            snapshot_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker         TEXT NOT NULL,
            captured_at    TEXT NOT NULL,
            source_ts      TEXT,
            quote_date     TEXT NOT NULL,
            spot           REAL,
            iv30           REAL,
            contract_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS underlying (
            snapshot_id     INTEGER PRIMARY KEY REFERENCES snapshots(snapshot_id),
            open            REAL,
            high            REAL,
            low             REAL,
            close           REAL,
            prev_day_close  REAL,
            volume          INTEGER,
            bid             REAL,
            ask             REAL,
            last_trade_time TEXT
        );

        CREATE TABLE IF NOT EXISTS contracts (
            snapshot_id       INTEGER NOT NULL REFERENCES snapshots(snapshot_id),
            expiry            TEXT NOT NULL,
            strike            REAL NOT NULL,
            type              TEXT NOT NULL,
            bid               REAL,
            ask               REAL,
            bid_size          REAL,
            ask_size          REAL,
            last_trade_price  REAL,
            last_trade_time   TEXT,
            volume            INTEGER,
            open_interest     INTEGER,
            iv                REAL,
            delta             REAL,
            gamma             REAL,
            theta             REAL,
            vega              REAL,
            rho               REAL,
            theo              REAL,
            PRIMARY KEY (snapshot_id, expiry, strike, type)
        ) WITHOUT ROWID;

        CREATE INDEX IF NOT EXISTS idx_snapshots_ticker
            ON snapshots(ticker, quote_date);
        """
    )

    for table in _APPEND_ONLY_TABLES:
        conn.executescript(
            f"""
            CREATE TRIGGER IF NOT EXISTS {table}_no_update
            BEFORE UPDATE ON {table}
            BEGIN SELECT RAISE(ABORT, 'archive is append-only: {table} cannot be updated'); END;

            CREATE TRIGGER IF NOT EXISTS {table}_no_delete
            BEFORE DELETE ON {table}
            BEGIN SELECT RAISE(ABORT, 'archive is append-only: {table} cannot be deleted from'); END;
            """
        )
    conn.commit()
    return conn


def _quote_date(source_ts: str | None, captured_at: str) -> str:
    """The trading date these quotes belong to. Prefer the exchange's own stamp."""
    stamp = source_ts or captured_at
    return stamp[:10]


def write_snapshot(ticker: str, raw: dict, contracts: list[dict]) -> int | None:
    """
    Append one chain snapshot. `raw` is the CBOE JSON, `contracts` the parsed list.
    Returns the new snapshot_id, or None if there was nothing to store.
    """
    if not contracts:
        return None

    data = raw.get("data", {})
    source_ts = raw.get("timestamp")
    captured_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO snapshots "
            "(ticker, captured_at, source_ts, quote_date, spot, iv30, contract_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ticker,
                captured_at,
                source_ts,
                _quote_date(source_ts, captured_at),
                data.get("current_price"),
                data.get("iv30"),
                len(contracts),
            ),
        )
        snapshot_id = cur.lastrowid

        conn.execute(
            "INSERT INTO underlying VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                data.get("open"), data.get("high"), data.get("low"), data.get("close"),
                data.get("prev_day_close"), data.get("volume"),
                data.get("bid"), data.get("ask"), data.get("last_trade_time"),
            ),
        )

        seen = set()
        rows = []
        for c in contracts:
            key = (c["expiry"], c["strike"], c["type"])
            if key in seen:
                continue
            seen.add(key)
            rows.append((
                snapshot_id, c["expiry"], c["strike"], c["type"],
                c.get("bid"), c.get("ask"), c.get("bid_size"), c.get("ask_size"),
                c.get("last"), c.get("last_trade_time"),
                c.get("volume"), c.get("open_interest"),
                c.get("iv"), c.get("delta"), c.get("gamma"),
                c.get("theta"), c.get("vega"), c.get("rho"), c.get("theoretical"),
            ))
        conn.executemany(
            "INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )

    return snapshot_id


def iv30_series(ticker: str, days: int = 365) -> list[tuple[str, float]]:
    """
    One (quote_date, iv30) per trading date, using the last snapshot of each date.

    Uses CBOE's own constant-maturity 30-day IV rather than a nearest-ATM
    front-month contract. Constant maturity is the right series for a rank: an
    ATM-contract series rolls between expiries, so it moves when the calendar
    moves and not only when volatility does.

    Deduplication is by snapshot_id, not captured_at — two captures inside the
    same second share a timestamp, so a MAX(captured_at) filter returns both.
    """
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT quote_date, iv30 FROM snapshots s
            WHERE ticker = ? AND quote_date >= ? AND iv30 IS NOT NULL
              AND snapshot_id = (
                  SELECT MAX(snapshot_id) FROM snapshots
                  WHERE ticker = s.ticker AND quote_date = s.quote_date AND iv30 IS NOT NULL
              )
            ORDER BY quote_date
            """,
            (ticker, cutoff),
        ).fetchall()
    return rows


def summary(ticker: str | None = None) -> list[dict]:
    """Per-ticker archive coverage."""
    with _conn() as conn:
        sql = """
            SELECT ticker,
                   COUNT(*)                        AS snapshots,
                   COUNT(DISTINCT quote_date)      AS trading_days,
                   MIN(quote_date)                 AS first_date,
                   MAX(quote_date)                 AS last_date,
                   SUM(contract_count)             AS contract_rows
            FROM snapshots
        """
        params = ()
        if ticker:
            sql += " WHERE ticker = ?"
            params = (ticker,)
        sql += " GROUP BY ticker ORDER BY ticker"
        rows = conn.execute(sql, params).fetchall()

    keys = ("ticker", "snapshots", "trading_days", "first_date", "last_date", "contract_rows")
    return [dict(zip(keys, r)) for r in rows]


def db_size_bytes() -> int:
    return DB_PATH.stat().st_size if DB_PATH.exists() else 0
