#!/usr/bin/env python3
"""
mx-options: TSX 60 options scanner (CBOE US-listed ADRs, USD).
"""

import argparse
import sys

from config import (
    CBOE_TO_TSX,
    DEFAULT_MIN_OI,
    MAX_SPREAD_PCT,
    RISK_FREE_RATE,
    UNIVERSE,
    TSX_TO_CBOE,
)
from analysis import greeks as gk
from analysis import metrics as mx
from analysis import scorer
from analysis import volatility as vol
from data import fetcher
from data import demo as demo_data
from output import display


def process_symbol(cboe_ticker: str, refresh: bool) -> list[dict]:
    """
    Full pipeline for one symbol:
      fetch → parse → fill Greeks → enrich metrics → return contracts.
    """
    try:
        contracts = fetcher.parse_options_chain(cboe_ticker, refresh=refresh)
    except RuntimeError as e:
        display.print_error(f"{cboe_ticker}: {e}")
        return []

    if not contracts:
        return []

    try:
        price_history = fetcher.fetch_price_history(cboe_ticker, refresh=refresh)
    except RuntimeError as e:
        display.print_error(f"{cboe_ticker} price history: {e}")
        price_history = []

    hv_data = vol.compute_hv(price_history) if price_history else {}
    mom20 = vol.momentum(price_history, 20) if price_history else None
    mom60 = vol.momentum(price_history, 60) if price_history else None

    spot = contracts[0].get("spot") if contracts else None
    atm = mx.atm_iv(contracts, spot)
    mx.update_iv_history(cboe_ticker, atm)
    ivr_val = mx.iv_rank(cboe_ticker, atm)
    ivp_val = mx.iv_percentile(cboe_ticker, atm)

    enriched = []
    for c in contracts:
        c = gk.fill_greeks(c, RISK_FREE_RATE)
        c = mx.enrich_contract(c, hv_data, mom20, mom60, ivr_val, ivp_val)
        enriched.append(c)

    return enriched


def apply_filters(
    contracts: list[dict],
    opt_type: str | None,
    moneyness: str | None,
    dte_min: int,
    dte_max: int,
    min_oi: int,
    sort_by: str,
) -> list[dict]:
    filtered = []
    for c in contracts:
        if c.get("spread_pct") is not None and c["spread_pct"] > MAX_SPREAD_PCT:
            continue
        if (c.get("open_interest") or 0) < min_oi:
            continue
        if opt_type and c.get("type") != opt_type.upper():
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

    sort_key_map = {
        "score": lambda c: c.get("score") or 0,
        "ivr": lambda c: c.get("ivr") or 0,
        "vrp": lambda c: -(c.get("vrp") or 0),  # most negative first
        "gamma": lambda c: c.get("gamma") or 0,
        "volume": lambda c: c.get("volume") or 0,
    }
    key_fn = sort_key_map.get(sort_by, sort_key_map["score"])
    return sorted(filtered, key=key_fn, reverse=True)


def process_demo_symbol(cboe_ticker: str) -> list[dict]:
    """Pipeline for --demo mode using synthetic data."""
    params = demo_data.DEMO_SYMBOLS.get(cboe_ticker, {"spot": 100.0, "hv30": 20.0, "iv_premium": 2.0})
    contracts = demo_data.make_chain(cboe_ticker, **params)
    price_history = demo_data.make_price_history(params["spot"], params["hv30"])

    hv_data = vol.compute_hv(price_history)
    mom20 = vol.momentum(price_history, 20)
    mom60 = vol.momentum(price_history, 60)

    spot = params["spot"]
    atm = mx.atm_iv(contracts, spot)
    ivr_val = None  # no history in demo mode
    ivp_val = None

    enriched = []
    for c in contracts:
        c = mx.enrich_contract(c, hv_data, mom20, mom60, ivr_val, ivp_val)
        enriched.append(c)
    return enriched


def cmd_scan(args: argparse.Namespace) -> None:
    all_contracts: list[dict] = []

    if args.demo:
        tickers = list(demo_data.DEMO_SYMBOLS.keys())
        display.print_info(f"[demo mode] {len(tickers)} symbols…")
        for cboe_ticker in tickers:
            contracts = process_demo_symbol(cboe_ticker)
            all_contracts.extend(scorer.score_all(contracts))
    else:
        tickers = UNIVERSE
        display.print_info(f"Scanning {len(tickers)} symbols…")
        for cboe_ticker in tickers:
            display.print_info(f"  {cboe_ticker}…")
            contracts = process_symbol(cboe_ticker, args.refresh)
            all_contracts.extend(scorer.score_all(contracts))

    filtered = apply_filters(
        all_contracts,
        opt_type=args.type,
        moneyness=args.moneyness,
        dte_min=args.dte_min,
        dte_max=args.dte_max,
        min_oi=args.min_oi,
        sort_by=args.sort,
    )

    top = filtered[: args.top]
    display.print_ranked_table(top, title=f"Top {args.top} Options Opportunities")


def cmd_symbol(args: argparse.Namespace) -> None:
    # Accept TSX or CBOE ticker
    cboe_ticker = args.symbol.upper()
    if cboe_ticker + ".TO" in TSX_TO_CBOE:
        cboe_ticker = TSX_TO_CBOE[cboe_ticker + ".TO"]
    elif cboe_ticker.endswith(".TO") and cboe_ticker in TSX_TO_CBOE:
        cboe_ticker = TSX_TO_CBOE[cboe_ticker]

    if args.demo:
        contracts = process_demo_symbol(cboe_ticker)
    else:
        contracts = process_symbol(cboe_ticker, args.refresh)
    if not contracts:
        display.print_error(f"No data for {args.symbol}")
        sys.exit(1)

    contracts = scorer.score_all(contracts)
    filtered = apply_filters(
        contracts,
        opt_type=args.type,
        moneyness=args.moneyness,
        dte_min=args.dte_min,
        dte_max=args.dte_max,
        min_oi=args.min_oi,
        sort_by=args.sort,
    )

    hv_data = {k: filtered[0].get(k) for k in ("hv10", "hv20", "hv30", "hv60")} if filtered else {}
    mom = {
        "mom20": filtered[0].get("mom20") if filtered else None,
        "mom60": filtered[0].get("mom60") if filtered else None,
    }
    display.print_symbol_detail(cboe_ticker, filtered, hv_data, mom)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mx-options",
        description="TSX 60 options scanner — CBOE US-listed ADRs (USD)",
    )
    p.add_argument("--symbol", "-s", metavar="TICKER",
                   help="Single-symbol deep-dive (TSX or CBOE ticker)")
    p.add_argument("--top", type=int, default=20, metavar="N",
                   help="Show top N results (default: 20)")
    p.add_argument("--type", choices=["call", "put", "C", "P"],
                   help="Filter by option type")
    p.add_argument("--moneyness", choices=["atm", "otm", "itm"],
                   help="Filter by moneyness")
    p.add_argument("--dte-min", type=int, default=0, metavar="DAYS",
                   help="Minimum DTE (default: 0)")
    p.add_argument("--dte-max", type=int, default=365, metavar="DAYS",
                   help="Maximum DTE (default: 365)")
    p.add_argument("--sort", choices=["score", "ivr", "vrp", "gamma", "volume"],
                   default="score", help="Sort column (default: score)")
    p.add_argument("--min-oi", type=int, default=DEFAULT_MIN_OI, metavar="N",
                   help=f"Minimum open interest (default: {DEFAULT_MIN_OI})")
    p.add_argument("--refresh", action="store_true",
                   help="Bypass cache and fetch fresh data")
    p.add_argument("--demo", action="store_true",
                   help="Use synthetic data (no network required)")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Normalize type arg
    if args.type == "call":
        args.type = "C"
    elif args.type == "put":
        args.type = "P"

    if args.symbol:
        cmd_symbol(args)
    else:
        cmd_scan(args)


if __name__ == "__main__":
    main()
