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
from zoneinfo import ZoneInfo

DB_PATH = Path(__file__).parent.parent / "archive" / "chains.db"

# CBOE stamps `timestamp` in UTC. The trading session it belongs to is an
# Eastern-time fact: a capture at 21:50 ET is 01:50 UTC the *following* calendar
# day, and taking source_ts[:10] files it under a session that has not happened
# yet. That inflates the trading-day count, and because iv30_series takes one
# observation per session date, it lets a single session contribute two points to
# the distribution that IVR and IVP are computed against.
_EXCHANGE_TZ = ZoneInfo("America/New_York")

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


def session_date(source_ts: str | None, captured_at: str) -> str:
    """
    The trading session these quotes belong to, as an Eastern-time date.

    Prefers the exchange's own stamp over our fetch time. Both are UTC, so both
    are converted before the date is taken — see _EXCHANGE_TZ above for why the
    naive `[:10]` was wrong.

    Note a remaining subtlety this does *not* solve: a capture taken before the
    09:30 ET open carries the previous session's quotes but stamps the current
    date. Pre-open captures are therefore mis-attributed by one session. The
    16:45 scheduled job is well clear of it; ad-hoc morning runs are not.
    """
    stamp = source_ts or captured_at
    try:
        parsed = datetime.datetime.fromisoformat(stamp)
    except ValueError:
        return stamp[:10]

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(_EXCHANGE_TZ).date().isoformat()


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
                session_date(source_ts, captured_at),
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
            SELECT snapshot_id, source_ts, captured_at, iv30 FROM snapshots
            WHERE ticker = ? AND quote_date >= ? AND iv30 IS NOT NULL
            ORDER BY snapshot_id
            """,
            (ticker, cutoff),
        ).fetchall()

    # Session date is recomputed here rather than read from the stored quote_date
    # column. The archive stores observations and derives everything else on read
    # precisely so a definition can be corrected without rewriting history — and
    # this definition was corrected (see session_date). Rows written under the old
    # UTC-naive rule are re-attributed to the right session by this path.
    #
    # Later snapshot_id wins within a session, so the last capture of the day is
    # the one that counts. Dedupe is by snapshot_id, not captured_at: two captures
    # inside the same second share a timestamp.
    latest: dict[str, tuple[int, float]] = {}
    for snapshot_id, source_ts, captured_at, iv30 in rows:
        day = session_date(source_ts, captured_at)
        if day not in latest or snapshot_id > latest[day][0]:
            latest[day] = (snapshot_id, iv30)
    return [(day, iv) for day, (_, iv) in sorted(latest.items())]


def summary(ticker: str | None = None) -> list[dict]:
    """
    Per-ticker archive coverage.

    Grouped in Python rather than SQL because trading_days must count *sessions*,
    and the session date is derived on read (see iv30_series). Counting DISTINCT
    quote_date in SQL would report the stored — and for evening captures, wrong —
    dates, overstating how much history a ticker actually has and unlocking
    IVR/IVP early off duplicate observations of one session.
    """
    with _conn() as conn:
        sql = "SELECT ticker, source_ts, captured_at, contract_count FROM snapshots"
        params = ()
        if ticker:
            sql += " WHERE ticker = ?"
            params = (ticker,)
        rows = conn.execute(sql, params).fetchall()

    acc: dict[str, dict] = {}
    for tkr, source_ts, captured_at, count in rows:
        day = session_date(source_ts, captured_at)
        a = acc.setdefault(tkr, {"snapshots": 0, "days": set(), "contract_rows": 0})
        a["snapshots"] += 1
        a["days"].add(day)
        a["contract_rows"] += count or 0

    return [
        {
            "ticker": tkr,
            "snapshots": a["snapshots"],
            "trading_days": len(a["days"]),
            "first_date": min(a["days"]),
            "last_date": max(a["days"]),
            "contract_rows": a["contract_rows"],
        }
        for tkr, a in sorted(acc.items())
    ]


def db_size_bytes() -> int:
    return DB_PATH.stat().st_size if DB_PATH.exists() else 0
