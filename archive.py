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
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from data import archive, fetcher
from output.display import console


def cmd_capture(args: argparse.Namespace) -> int:
    tickers = [t.upper() for t in args.tickers]
    if args.from_archive:
        tickers = sorted({row["ticker"] for row in archive.summary()} | set(tickers))

    if not tickers:
        console.print("[bold red]Error:[/bold red] no tickers given, and the archive is empty.")
        return 1

    failures = 0
    for ticker in tickers:
        try:
            raw, contracts = fetcher.fetch_chain_with_raw(ticker, refresh=True)
            snapshot_id = archive.write_snapshot(ticker, raw, contracts)
            if snapshot_id is None:
                console.print(f"  [yellow]{ticker}: no contracts returned[/yellow]")
                failures += 1
            else:
                iv30 = raw.get("data", {}).get("iv30")
                iv_str = f"iv30 {iv30:.1f}%" if iv30 else "iv30 —"
                console.print(f"  [green]{ticker}[/green]  {len(contracts):>5} contracts  {iv_str}")
        except Exception as e:
            console.print(f"  [bold red]{ticker}: {e}[/bold red]")
            failures += 1

    console.print(
        f"\n  {len(tickers) - failures}/{len(tickers)} captured   "
        f"archive {archive.db_size_bytes() / 1e6:.1f} MB"
    )
    return 1 if failures == len(tickers) else 0


def cmd_status(args: argparse.Namespace) -> int:
    from rich.table import Table
    from rich import box

    rows = archive.summary(args.ticker.upper() if args.ticker else None)
    if not rows:
        console.print("  [dim]Archive is empty. Try: python archive.py capture AAPL[/dim]")
        return 0

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

        table.add_row(
            r["ticker"], f"{r['snapshots']:,}", f"{days:,}",
            r["first_date"], r["last_date"], f"{r['contract_rows']:,}",
            f"[{style}]{readiness}[/{style}]",
        )

    console.print(table)
    console.print(
        f"  [dim]{archive.db_size_bytes() / 1e6:.1f} MB on disk. "
        f"IV rank and percentile need 10+ days to report at all, and a full year "
        f"before the range means what its name implies.[/dim]"
    )
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="archive", description="Point-in-time chain archive")
    sub = p.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="Fetch and append snapshots")
    cap.add_argument("tickers", nargs="*", help="Tickers to capture")
    cap.add_argument("--from-archive", action="store_true",
                     help="Also capture every ticker already in the archive")
    cap.set_defaults(func=cmd_capture)

    st = sub.add_parser("status", help="Show archive coverage")
    st.add_argument("ticker", nargs="?", help="Limit to one ticker")
    st.set_defaults(func=cmd_status)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
