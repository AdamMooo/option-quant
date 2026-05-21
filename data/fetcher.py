"""
Data fetching layer. Two sources:
  - CBOE CDN: delayed options chains for US-listed Canadian ADRs
  - yfinance: daily price history for HV calculation
"""

import datetime
import time

import requests
import yfinance as yf

from config import CACHE_TTL_OPTIONS, CACHE_TTL_PRICES, CBOE_API_URL
from data import cache

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_options_chain(cboe_ticker: str, refresh: bool = False) -> dict:
    """
    Returns raw CBOE JSON for a ticker.
    Raises RuntimeError on non-200 or missing data.
    """
    if not refresh:
        cached = cache.get_options(cboe_ticker, CACHE_TTL_OPTIONS)
        if cached is not None:
            return cached

    url = CBOE_API_URL.format(ticker=cboe_ticker)
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(
            f"CBOE returned {resp.status_code} for {cboe_ticker}: {resp.text[:200]}"
        )

    data = resp.json()
    if "data" not in data:
        raise RuntimeError(f"Unexpected CBOE response shape for {cboe_ticker}")

    cache.set_options(cboe_ticker, data)
    return data


def fetch_price_history(cboe_ticker: str, days: int = 380, refresh: bool = False) -> list[dict]:
    """
    Returns list of {date, close} dicts (chronological) from yfinance.
    Uses the CBOE ticker directly — matches US-listed symbol.
    """
    if not refresh:
        cached = cache.get_prices(cboe_ticker, CACHE_TTL_PRICES)
        if cached is not None:
            return cached

    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)

    ticker = yf.Ticker(cboe_ticker)
    hist = ticker.history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True)

    if hist.empty:
        raise RuntimeError(f"yfinance returned no data for {cboe_ticker}")

    records = [
        {"date": str(idx.date()), "close": float(row["Close"])}
        for idx, row in hist.iterrows()
    ]

    cache.set_prices(cboe_ticker, records)
    return records


def fetch_spot_price(cboe_ticker: str) -> float:
    """Returns current spot price from CBOE options data (underlying price)."""
    data = fetch_options_chain(cboe_ticker)
    spot = data.get("data", {}).get("current_price")
    if spot:
        return float(spot)
    # Fallback: latest close from yfinance
    hist = fetch_price_history(cboe_ticker, days=5)
    if hist:
        return hist[-1]["close"]
    raise RuntimeError(f"Cannot determine spot price for {cboe_ticker}")


def parse_options_chain(cboe_ticker: str, refresh: bool = False) -> list[dict]:
    """
    Parses the CBOE JSON into a flat list of contract dicts.
    Each dict has: ticker, expiry, dte, strike, type, bid, ask, mid,
    last, volume, open_interest, iv, delta, gamma, theta, vega, rho,
    theoretical, spread_pct.

    If CBOE provides iv/greeks, they are used directly.
    Fields absent from CBOE are set to None (greeks.py fills them in).
    """
    data = fetch_options_chain(cboe_ticker, refresh=refresh)
    raw = data.get("data", {})
    spot = raw.get("current_price", None)
    today = datetime.date.today()

    contracts = []
    for exp_block in raw.get("options", []):
        expiry_str = exp_block.get("expiration_date", "")
        try:
            expiry = datetime.date.fromisoformat(expiry_str)
        except ValueError:
            continue
        dte = (expiry - today).days
        if dte < 0:
            continue

        for opt in exp_block.get("option", []):
            call_put = opt.get("option_type", "").upper()
            if call_put not in ("C", "P"):
                # Some CBOE responses use "call"/"put"
                raw_type = opt.get("option_type", "")
                call_put = "C" if raw_type.lower().startswith("c") else "P"

            bid = opt.get("bid", 0.0) or 0.0
            ask = opt.get("ask", 0.0) or 0.0
            mid = (bid + ask) / 2 if (bid + ask) > 0 else None
            spread_pct = ((ask - bid) / mid * 100) if (mid and mid > 0) else None

            contracts.append(
                {
                    "ticker": cboe_ticker,
                    "expiry": expiry_str,
                    "dte": dte,
                    "strike": opt.get("strike", 0.0),
                    "type": call_put,
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "last": opt.get("last_trade_price") or opt.get("last"),
                    "volume": opt.get("volume", 0) or 0,
                    "open_interest": opt.get("open_interest", 0) or 0,
                    "iv": opt.get("iv") or opt.get("implied_volatility"),
                    "delta": opt.get("delta"),
                    "gamma": opt.get("gamma"),
                    "theta": opt.get("theta"),
                    "vega": opt.get("vega"),
                    "rho": opt.get("rho"),
                    "theoretical": opt.get("theoretical"),
                    "spread_pct": spread_pct,
                    "spot": spot,
                }
            )

    return contracts
