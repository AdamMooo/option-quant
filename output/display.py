"""
Rich terminal output: ranked table and single-symbol detail view.
"""

from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

console = Console(width=160)


def print_macro_header(macro: dict) -> None:
    from data.macro import vix_regime, term_structure

    vix = macro.get("vix")
    vix3m = macro.get("vix3m")
    y10 = macro.get("yield_10y")
    ff = macro.get("fed_funds")

    regime = vix_regime(vix)
    regime_style = {"low": "green", "normal": "yellow", "elevated": "bold yellow", "high": "bold red"}.get(regime, "dim")
    ts = term_structure(vix, vix3m)
    ts_style = "green" if ts == "contango" else "bold red" if ts == "backwardation" else "dim"

    vix_str = f"[{regime_style}]VIX {_fmt(vix, '.1f')} ({regime})[/{regime_style}]"
    vix3m_str = f"VIX3M {_fmt(vix3m, '.1f')}  [{ts_style}]{ts}[/{ts_style}]"
    y10_str = f"10Y {_fmt(y10, '.2f')}%"
    ff_str = f"Fed Funds {_fmt(ff, '.2f')}%"

    console.print(f"  {vix_str}   {vix3m_str}   {y10_str}   {ff_str}", highlight=False)
    console.print()


def _score_style(score: float | None) -> str:
    if score is None:
        return "dim"
    if score >= 75:
        return "bold green"
    if score >= 50:
        return "yellow"
    return "dim"


def _fmt(val, fmt: str = ".2f", fallback: str = "—") -> str:
    if val is None:
        return fallback
    try:
        return format(val, fmt)
    except (TypeError, ValueError):
        return fallback


def _sign(val: float | None) -> str:
    if val is None:
        return "—"
    return f"+{val:.2f}" if val >= 0 else f"{val:.2f}"


def print_ranked_table(contracts: list[dict], title: str = "Options Scanner") -> None:
    table = Table(
        title=title,
        box=box.SIMPLE_HEAD,
        show_lines=False,
        header_style="bold cyan",
        pad_edge=False,
    )

    columns = [
        ("Symbol", "left"),
        ("Expiry", "center"),
        ("DTE", "right"),
        ("Strike", "right"),
        ("T", "center"),
        ("Score", "right"),
        ("IV%", "right"),
        ("IVR", "right"),
        ("VRP", "right"),
        ("Delta", "right"),
        ("Gamma", "right"),
        ("Theta", "right"),
        ("Vol", "right"),
        ("OI", "right"),
        ("Sprd%", "right"),
    ]
    for name, justify in columns:
        table.add_column(name, justify=justify, no_wrap=True)

    for c in contracts:
        score = c.get("score")
        style = _score_style(score)

        def cell(val, fmt=".2f", fallback="—"):
            return Text(_fmt(val, fmt, fallback), style=style)

        table.add_row(
            Text(c.get("ticker", ""), style=style),
            Text(c.get("expiry", "")[-5:], style=style),   # MM-DD
            Text(str(c.get("dte", "")), style=style),
            Text(_fmt(c.get("strike"), ".1f"), style=style),
            Text(c.get("type", ""), style=style),
            Text(_fmt(score, ".0f"), style="bold green" if (score or 0) >= 75 else style),
            cell(c.get("iv"), ".1f"),
            cell(c.get("ivr"), ".0f"),
            Text(_sign(c.get("vrp")), style=style),
            cell(c.get("delta"), ".3f"),
            cell(c.get("gamma"), ".4f"),
            cell(c.get("theta"), ".3f"),
            Text(f"{int(c.get('volume') or 0):,}", style=style),
            Text(f"{int(c.get('open_interest') or 0):,}", style=style),
            cell(c.get("spread_pct"), ".1f"),
        )

    console.print(table)


def print_symbol_detail(symbol: str, contracts: list[dict], hv_data: dict, mom: dict) -> None:
    """Full chain + stock context for a single symbol."""
    console.rule(f"[bold cyan]{symbol} — Full Option Chain[/bold cyan]")

    # Stock context block
    console.print(
        f"  Spot: [bold]{_fmt(contracts[0].get('spot') if contracts else None, '.2f')}[/bold]  "
        f"HV10: {_fmt(hv_data.get('hv10'), '.1f')}%  "
        f"HV20: {_fmt(hv_data.get('hv20'), '.1f')}%  "
        f"HV30: {_fmt(hv_data.get('hv30'), '.1f')}%  "
        f"HV60: {_fmt(hv_data.get('hv60'), '.1f')}%  "
        f"Mom20: {_sign(mom.get('mom20'))}%  "
        f"Mom60: {_sign(mom.get('mom60'))}%"
    )
    console.print()

    print_ranked_table(contracts, title=f"{symbol} Contracts")


def print_error(msg: str) -> None:
    console.print(f"[bold red]Error:[/bold red] {msg}")


def print_info(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]")
