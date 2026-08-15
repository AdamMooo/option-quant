#!/usr/bin/env python3
"""
Archive maintenance: capture snapshots, inspect coverage.

The archive is the repo's long-lived asset. `main.py` captures a snapshot every
time you look at a symbol, but that is opportunistic — to build a real IV history
you need to capture on a schedule, whether or not you happened to look.

    python archive.py capture AAPL MSFT NVDA
    python archive.py capture --from-archive     # everything already tracked
    python archive.py status
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from data import archive, fetcher
from data.seed import CAPTURE_SEED
from output.display import console

# Between symbols. At ~120 names a run is minutes either way, and being throttled
# or blocked costs every name that night, not one.
THROTTLE_SEC = 0.4

# A transient fetch failure is a permanently lost day for that ticker — there is
# no backfill. Cheap to retry, expensive not to.
RETRY_DELAYS = (2, 5)

# Above this share of failures the run is treated as systemically broken and the
# process exits nonzero. Below it, individual dead tickers are logged and caught
# by `status`, which flags staleness per ticker. A job that reports failure
# because one illiquid name delisted is a job you learn to ignore.
FAILURE_RATE_ALERT = 0.10


def _capture_one(ticker: str) -> tuple[bool, str]:
    """Returns (ok, message). Retries transient failures."""
    last_err = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            raw, contracts = fetcher.fetch_chain_with_raw(ticker, refresh=True)
            snapshot_id = archive.write_snapshot(ticker, raw, contracts)
            if snapshot_id is None:
                return False, "no contracts returned"
            iv30 = raw.get("data", {}).get("iv30")
            iv_str = f"iv30 {iv30:.1f}%" if iv30 else "iv30 —"
            retried = f" (attempt {attempt + 1})" if attempt else ""
            return True, f"{len(contracts):>5} contracts  {iv_str}{retried}"
        except Exception as e:
            last_err = e
            if attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])
    return False, str(last_err)


def cmd_capture(args: argparse.Namespace) -> int:
    tickers = {t.upper() for t in args.tickers}
    if args.from_archive:
        tickers |= {row["ticker"] for row in archive.summary()}
    if args.seed:
        tickers |= set(CAPTURE_SEED)
    tickers = sorted(tickers)

    if not tickers:
        console.print("[bold red]Error:[/bold red] no tickers given, and the archive is empty.")
        return 1

    failed = []
    for i, ticker in enumerate(tickers):
        if i:
            time.sleep(THROTTLE_SEC)
        ok, msg = _capture_one(ticker)
        if ok:
            console.print(f"  [green]{ticker:<6}[/green] {msg}")
        else:
            console.print(f"  [bold red]{ticker:<6}[/bold red] {msg}")
            failed.append(ticker)

    captured = len(tickers) - len(failed)
    console.print(
        f"\n  {captured}/{len(tickers)} captured   "
        f"archive {archive.db_size_bytes() / 1e6:.1f} MB"
    )
    if failed:
        console.print(f"  [yellow]failed:[/yellow] {' '.join(failed)}")

    rate = len(failed) / len(tickers)
    if rate > FAILURE_RATE_ALERT:
        console.print(
            f"  [bold red]{rate:.0%} of the run failed — treating as systemic.[/bold red]"
        )
        return 1
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from rich.table import Table
    from rich import box

    rows = archive.summary(args.ticker.upper() if args.ticker else None)
    if not rows:
        console.print("  [dim]Archive is empty. Try: python archive.py capture AAPL[/dim]")
        return 0

    # Staleness is measured against the rest of the archive, not the wall clock:
    # on a holiday every ticker is a day behind and nothing is wrong. A ticker
    # that has silently stopped updating falls behind its peers.
    #
    # Taken over the whole archive, not `rows` — filtering to one ticker would
    # otherwise make it its own reference and it could never be flagged.
    latest = max(r["last_date"] for r in archive.summary())
    stale = [r["ticker"] for r in rows if r["last_date"] < latest]

    table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", pad_edge=False)
    for name in ("Ticker", "Snapshots", "Days", "First", "Last", "Contract rows", "IVR/IVP"):
        table.add_column(name, justify="right" if name != "Ticker" else "left")

    for r in rows:
        days = r["trading_days"]
        # The threshold that gates iv_rank / iv_percentile in analysis/metrics.py.
        if days >= 252:
            readiness, style = "full year", "bold green"
        elif days >= 10:
            readiness, style = f"thin ({days}d)", "yellow"
        else:
            readiness, style = f"no ({days}d)", "dim"

        last = r["last_date"]
        table.add_row(
            r["ticker"], f"{r['snapshots']:,}", f"{days:,}",
            r["first_date"],
            f"[bold red]{last}[/bold red]" if last < latest else last,
            f"{r['contract_rows']:,}",
            f"[{style}]{readiness}[/{style}]",
        )

    console.print(table)
    console.print(
        f"  [dim]{archive.db_size_bytes() / 1e6:.1f} MB on disk. "
        f"IV rank and percentile need 10+ days to report at all, and a full year "
        f"before the range means what its name implies.[/dim]"
    )
    if stale:
        console.print(
            f"  [bold red]{len(stale)} ticker(s) behind {latest}:[/bold red] "
            f"{' '.join(stale)}"
        )
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="archive", description="Point-in-time chain archive")
    sub = p.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="Fetch and append snapshots")
    cap.add_argument("tickers", nargs="*", help="Tickers to capture")
    cap.add_argument("--from-archive", action="store_true",
                     help="Also capture every ticker already in the archive")
    cap.add_argument("--seed", action="store_true",
                     help="Also capture the seed list (data/seed.py) — use once to enrol")
    cap.set_defaults(func=cmd_capture)

    st = sub.add_parser("status", help="Show archive coverage")
    st.add_argument("ticker", nargs="?", help="Limit to one ticker")
    st.set_defaults(func=cmd_status)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
