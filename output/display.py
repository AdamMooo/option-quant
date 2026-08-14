"""
Rich terminal output for the single-symbol option market view.

Describes; does not rank. The composite Score / Q / D columns were removed
2026-08-14 — see the post-mortem in options-quant.md.
"""

from rich.console import Console
from rich.table import Table
from rich import box

console = Console(width=150)


def _fmt(val, fmt: str = ".2f", fallback: str = "—") -> str:
    if val is None:
        return fallback
    try:
        return format(val, fmt)
    except (TypeError, ValueError):
        return fallback


def _sign(val: float | None, fmt: str = ".2f") -> str:
    if val is None:
        return "—"
    return f"+{format(val, fmt)}" if val >= 0 else format(val, fmt)


def print_macro_header(macro: dict) -> None:
    from data.macro import vix_regime, term_structure

    vix = macro.get("vix")
    vix3m = macro.get("vix3m")

    regime = vix_regime(vix)
    regime_style = {"low": "green", "normal": "yellow", "elevated": "bold yellow", "high": "bold red"}.get(regime, "dim")
    ts = term_structure(vix, vix3m)
    ts_style = "green" if ts == "contango" else "bold red" if ts == "backwardation" else "dim"

    console.print(
        f"  [{regime_style}]VIX {_fmt(vix, '.1f')} ({regime})[/{regime_style}]   "
        f"VIX3M {_fmt(vix3m, '.1f')}  [{ts_style}]{ts}[/{ts_style}]   "
        f"10Y {_fmt(macro.get('yield_10y'), '.2f')}%   "
        f"Fed Funds {_fmt(macro.get('fed_funds'), '.2f')}%",
        highlight=False,
    )


def print_symbol_header(
    symbol: str,
    spot: float | None,
    hv: dict,
    atm: float | None,
    ivr: float | None,
    ivp: float | None,
    iv_depth: int,
    days_to_earnings: int | None,
    jump: dict | None = None,
) -> None:
    console.rule(f"[bold cyan]{symbol}[/bold cyan]")

    console.print(
        f"  Spot [bold]{_fmt(spot)}[/bold]    "
        f"Realized vol  10d {_fmt(hv.get('hv10'), '.1f')}%  "
        f"20d {_fmt(hv.get('hv20'), '.1f')}%  "
        f"30d {_fmt(hv.get('hv30'), '.1f')}%  "
        f"60d {_fmt(hv.get('hv60'), '.1f')}%",
        highlight=False,
    )

    vrp_atm = round(atm - hv["hv30"], 2) if (atm is not None and hv.get("hv30")) else None
    console.print(
        f"  ATM IV [bold]{_fmt(atm, '.1f')}%[/bold]    "
        f"vs 30d realized: [bold]{_sign(vrp_atm, '.1f')}[/bold] vol pts",
        highlight=False,
    )

    # Realized vol is backward-looking and jump-sensitive; implied is forward-looking.
    # If one day dominates the window, say so rather than let the gap read as a signal.
    if jump and abs(jump["move_pct"]) >= 4.0 and hv.get("hv30"):
        delta = hv["hv30"] - jump["hv_ex_jump"]
        console.print(
            f"  [yellow]Caution:[/yellow] [dim]a single {jump['move_pct']:+.1f}% day "
            f"({jump['date']}) accounts for {delta:.1f} of those {hv['hv30']:.1f} vol pts. "
            f"Ex-that-day 30d realized is {jump['hv_ex_jump']:.1f}%. Realized looks back; "
            f"implied looks forward — check whether both windows contain the same events.[/dim]",
            highlight=False,
        )

    if iv_depth < 10:
        console.print(
            f"  [dim]IV rank / percentile: unavailable — only {iv_depth} stored IV "
            f"observation(s) for {symbol}. Needs 10+; a real 52-week read needs a year.[/dim]",
            highlight=False,
        )
    else:
        console.print(
            f"  IV Rank {_fmt(ivr, '.0f')}   IV Percentile {_fmt(ivp, '.0f')}   "
            f"[dim](from {iv_depth} stored observations)[/dim]",
            highlight=False,
        )

    if days_to_earnings is not None:
        style = "bold red" if days_to_earnings < 14 else "yellow" if days_to_earnings < 30 else "dim"
        console.print(f"  [{style}]Earnings in {days_to_earnings} days[/{style}]", highlight=False)
    else:
        console.print("  [dim]Earnings date unknown (no FINNHUB_API_KEY, or none scheduled)[/dim]")


def print_news(items: list[dict]) -> None:
    if not items:
        return
    console.print()
    console.print("  [bold cyan]Recent news[/bold cyan]")
    for a in items:
        headline = a["headline"][:110]
        console.print(f"  [dim]{a['date']}[/dim]  {headline}  [dim]({a['source']})[/dim]", highlight=False)


def print_chain(contracts: list[dict], title: str) -> None:
    table = Table(
        title=title,
        box=box.SIMPLE_HEAD,
        show_lines=False,
        header_style="bold cyan",
        pad_edge=False,
    )

    columns = [
        ("Expiry", "center"), ("DTE", "right"), ("Strike", "right"), ("T", "center"),
        ("Bid", "right"), ("Ask", "right"), ("Sprd%", "right"),
        ("IV%", "right"), ("VRP", "right"),
        ("Delta", "right"), ("Gamma", "right"), ("Theta", "right"), ("Vega", "right"),
        ("Vol", "right"), ("OI", "right"),
    ]
    for name, justify in columns:
        table.add_column(name, justify=justify, no_wrap=True)

    for c in contracts:
        # Wide markets are dimmed — you cannot trade what you cannot get filled on.
        style = "dim" if (c.get("spread_pct") or 0) > 10 else ""

        table.add_row(
            c.get("expiry", ""),
            str(c.get("dte", "")),
            _fmt(c.get("strike"), ".1f"),
            c.get("type", ""),
            _fmt(c.get("bid")),
            _fmt(c.get("ask")),
            _fmt(c.get("spread_pct"), ".1f"),
            _fmt(c.get("iv"), ".1f"),
            _sign(c.get("vrp"), ".1f"),
            _fmt(c.get("delta"), ".3f"),
            _fmt(c.get("gamma"), ".4f"),
            _fmt(c.get("theta"), ".3f"),
            _fmt(c.get("vega"), ".3f"),
            f"{int(c.get('volume') or 0):,}",
            f"{int(c.get('open_interest') or 0):,}",
            style=style,
        )

    console.print(table)
    console.print(
        "  [dim]VRP = contract IV minus 30d realized vol, in vol points. "
        "Dimmed rows have a bid-ask spread wider than 10% of mid.[/dim]",
        highlight=False,
    )


def print_error(msg: str) -> None:
    console.print(f"[bold red]Error:[/bold red] {msg}")


def print_info(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]")
