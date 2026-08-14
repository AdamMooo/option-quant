#!/usr/bin/env python3
"""
options-quant: single-stock option market view.

One ticker in, the state of its option market out. No universe scan, no ranking,
no composite score — see options-quant.md.
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from config import DEFAULT_MIN_OI, MAX_SPREAD_PCT, RISK_FREE_RATE
from analysis import greeks as gk
from analysis import metrics as mx
from analysis import volatility as vol
from data import fetcher
from data import demo as demo_data
from data import macro as macro_data
from output import display


def process_symbol(ticker: str, refresh: bool) -> tuple[list[dict], dict]:
    """
    Full pipeline for one symbol: fetch → parse → fill Greeks → enrich.
    Returns (contracts, context).
    """
    contracts = fetcher.parse_options_chain(ticker, refresh=refresh)
    if not contracts:
        return [], {}

    try:
        price_history = fetcher.fetch_price_history(ticker, refresh=refresh)
    except RuntimeError as e:
        display.print_error(f"{ticker} price history: {e}")
        price_history = []

    hv_data = vol.compute_hv(price_history) if price_history else {}

    spot = contracts[0].get("spot")
    atm = mx.atm_iv(contracts, spot)
    mx.update_iv_history(ticker, atm)

    context = {
        "spot": spot,
        "hv": hv_data,
        "atm_iv": atm,
        "ivr": mx.iv_rank(ticker, atm),
        "ivp": mx.iv_percentile(ticker, atm),
        "iv_depth": mx.iv_history_depth(ticker),
        "days_to_earnings": fetcher.fetch_next_earnings(ticker),
        "news": fetcher.fetch_company_news(ticker),
        "jump": vol.largest_move(price_history) if price_history else None,
    }

    enriched = [
        mx.enrich_contract(gk.fill_greeks(c, RISK_FREE_RATE), hv_data, context["ivr"], context["ivp"])
        for c in contracts
    ]
    return enriched, context


def process_demo_symbol(ticker: str) -> tuple[list[dict], dict]:
    params = demo_data.DEMO_SYMBOLS.get(ticker, {"spot": 100.0, "hv30": 20.0, "iv_premium": 2.0})
    contracts = demo_data.make_chain(ticker, **params)
    price_history = demo_data.make_price_history(params["spot"], params["hv30"])
    hv_data = vol.compute_hv(price_history)

    atm = mx.atm_iv(contracts, params["spot"])
    context = {
        "spot": params["spot"],
        "hv": hv_data,
        "atm_iv": atm,
        "ivr": None,
        "ivp": None,
        "iv_depth": 0,
        "days_to_earnings": None,
        "news": [],
        "jump": vol.largest_move(price_history),
    }
    enriched = [mx.enrich_contract(c, hv_data, None, None) for c in contracts]
    return enriched, context


def apply_filters(
    contracts: list[dict],
    opt_type: str | None,
    moneyness: str | None,
    dte_min: int,
    dte_max: int,
    min_oi: int,
    sort_by: str,
) -> list[dict]:
    """Narrows the chain to what is worth looking at. These are visibility filters,
    not a quality judgement."""
    filtered = []
    for c in contracts:
        if c.get("spread_pct") is not None and c["spread_pct"] > MAX_SPREAD_PCT:
            continue
        iv = c.get("iv") or 0
        if iv <= 0:
            continue
        if (c.get("open_interest") or 0) < min_oi:
            continue
        if opt_type and c.get("type") != opt_type:
            continue
        dte = c.get("dte", 0)
        if dte < dte_min or dte > dte_max:
            continue

        spot = c.get("spot")
        strike = c.get("strike")
        if moneyness and spot and strike:
            ratio = strike / spot
            if moneyness == "otm":
                if c["type"] == "C" and ratio <= 1.0:
                    continue
                if c["type"] == "P" and ratio >= 1.0:
                    continue
            elif moneyness == "itm":
                if c["type"] == "C" and ratio >= 1.0:
                    continue
                if c["type"] == "P" and ratio <= 1.0:
                    continue
            elif moneyness == "atm":
                if abs(ratio - 1.0) > 0.03:
                    continue
        filtered.append(c)

    if sort_by == "chain":
        return sorted(filtered, key=lambda c: (c.get("dte", 0), c.get("type", ""), c.get("strike", 0)))

    sort_key_map = {
        "iv": lambda c: c.get("iv") or 0,
        "vrp": lambda c: c.get("vrp") or 0,
        "gamma": lambda c: c.get("gamma") or 0,
        "vega": lambda c: c.get("vega") or 0,
        "volume": lambda c: c.get("volume") or 0,
        "oi": lambda c: c.get("open_interest") or 0,
        "spread": lambda c: -(c.get("spread_pct") or 0),
    }
    return sorted(filtered, key=sort_key_map[sort_by], reverse=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="options-quant",
        description="Single-stock option market view — describes, does not rank",
    )
    p.add_argument("symbol", nargs="?", help="Stock ticker (e.g. SHOP)")
    p.add_argument("--type", choices=["call", "put"], help="Filter by option type")
    p.add_argument("--moneyness", choices=["atm", "otm", "itm"], help="Filter by moneyness")
    p.add_argument("--dte-min", type=int, default=0, metavar="DAYS", help="Minimum DTE (default: 0)")
    p.add_argument("--dte-max", type=int, default=365, metavar="DAYS", help="Maximum DTE (default: 365)")
    p.add_argument(
        "--sort",
        choices=["chain", "iv", "vrp", "gamma", "vega", "volume", "oi", "spread"],
        default="chain",
        help="Sort order (default: chain — by expiry, then type, then strike)",
    )
    p.add_argument("--min-oi", type=int, default=DEFAULT_MIN_OI, metavar="N",
                   help=f"Minimum open interest (default: {DEFAULT_MIN_OI})")
    p.add_argument("--limit", type=int, default=60, metavar="N",
                   help="Max rows to display (default: 60)")
    p.add_argument("--refresh", action="store_true", help="Bypass cache and fetch fresh data")
    p.add_argument("--demo", action="store_true", help="Use synthetic data (no network required)")
    return p


def main() -> None:
    args = build_parser().parse_args()

    if not args.symbol:
        if not args.demo:
            display.print_error("A ticker is required. Try: python main.py SHOP")
            sys.exit(1)
        args.symbol = "SHOP"

    ticker = args.symbol.upper()
    opt_type = {"call": "C", "put": "P"}.get(args.type)

    if args.demo:
        contracts, ctx = process_demo_symbol(ticker)
    else:
        try:
            contracts, ctx = process_symbol(ticker, args.refresh)
        except RuntimeError as e:
            display.print_error(f"{ticker}: {e}")
            sys.exit(1)

    if not contracts:
        display.print_error(f"No option data for {ticker}")
        sys.exit(1)

    filtered = apply_filters(
        contracts,
        opt_type=opt_type,
        moneyness=args.moneyness,
        dte_min=args.dte_min,
        dte_max=args.dte_max,
        min_oi=args.min_oi,
        sort_by=args.sort,
    )

    if not args.demo:
        display.print_macro_header(macro_data.fetch_macro())

    display.print_symbol_header(
        ticker, ctx["spot"], ctx["hv"], ctx["atm_iv"],
        ctx["ivr"], ctx["ivp"], ctx["iv_depth"], ctx["days_to_earnings"], ctx["jump"],
    )
    display.print_news(ctx["news"])

    shown = filtered[: args.limit]
    title = f"{ticker} — {len(shown)} of {len(filtered)} contracts passing filters"
    display.print_chain(shown, title=title)


if __name__ == "__main__":
    main()
