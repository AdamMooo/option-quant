"""
Data fetching layer. Sources:
  - CBOE CDN: delayed options chains
  - yfinance: daily price history for realized vol
  - Finnhub: next earnings date + recent company news
"""

import datetime
import os
import time

import requests
import yfinance as yf

from config import CACHE_TTL_OPTIONS, CACHE_TTL_PRICES, CBOE_API_URL
from data import cache

_FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")
_FINNHUB_TTL = 6 * 60 * 60  # 6 hours

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


def fetch_next_earnings(cboe_ticker: str) -> int | None:
    """
    Returns days until next earnings, or None if unknown.
    Uses Finnhub earnings calendar. Results cached 6h.
    """
    if not _FINNHUB_KEY:
        return None

    cache_key = f"earnings_{cboe_ticker}"
    cached = cache.get_generic(cache_key, _FINNHUB_TTL)
    if cached is not None:
        return cached

    today = datetime.date.today()
    to_date = today + datetime.timedelta(days=90)
    url = (
        f"https://finnhub.io/api/v1/calendar/earnings"
        f"?from={today}&to={to_date}&symbol={cboe_ticker}"
        f"&token={_FINNHUB_KEY}"
    )
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json()
        events = data.get("earningsCalendar", [])
        if not events:
            cache.set_generic(cache_key, None)
            return None
        # First upcoming event
        dates = sorted(
            e["date"] for e in events if e.get("date") and e["date"] >= str(today)
        )
        if not dates:
            cache.set_generic(cache_key, None)
            return None
        next_date = datetime.date.fromisoformat(dates[0])
        days_away = (next_date - today).days
        cache.set_generic(cache_key, days_away)
        return days_away
    except Exception:
        return None


def fetch_company_news(cboe_ticker: str, days: int = 14, limit: int = 8) -> list[dict]:
    """
    Recent company news headlines from Finnhub, newest first.
    Returns [] if no API key or on any failure — news is context, never load-bearing.
    """
    if not _FINNHUB_KEY:
        return []

    cache_key = f"news_{cboe_ticker}"
    cached = cache.get_generic(cache_key, _FINNHUB_TTL)
    if cached is not None:
        return cached[:limit]

    today = datetime.date.today()
    frm = today - datetime.timedelta(days=days)
    url = (
        f"https://finnhub.io/api/v1/company-news"
        f"?symbol={cboe_ticker}&from={frm}&to={today}&token={_FINNHUB_KEY}"
    )
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return []
        items = [
            {
                "date": datetime.date.fromtimestamp(a["datetime"]).isoformat(),
                "headline": a.get("headline", ""),
                "source": a.get("source", ""),
            }
            for a in resp.json()
            if a.get("datetime") and a.get("headline")
        ]
        items.sort(key=lambda a: a["date"], reverse=True)
        cache.set_generic(cache_key, items)
        return items[:limit]
    except Exception:
        return []


def _parse_occ_symbol(occ: str) -> tuple[str, str, float] | None:
    """
    Decode an OCC option symbol: <root><YYMMDD><C|P><strike*1000 zero-padded to 8>.
    Returns (expiry_iso, call_put, strike) or None on parse failure.
    """
    import re
    m = re.search(r"(\d{6})([CP])(\d{8})$", occ)
    if not m:
        return None
    date_str, call_put, strike_raw = m.groups()
    try:
        expiry = datetime.datetime.strptime(date_str, "%y%m%d").date()
    except ValueError:
        return None
    strike = int(strike_raw) / 1000.0
    return expiry.isoformat(), call_put, strike


def parse_options_chain(cboe_ticker: str, refresh: bool = False) -> list[dict]:
    """
    Parses the CBOE JSON into a flat list of contract dicts.
    Each dict has: ticker, expiry, dte, strike, type, bid, ask, mid,
    last, volume, open_interest, iv, delta, gamma, theta, vega, rho,
    theoretical, spread_pct.

    If CBOE provides iv/greeks, they are used directly.
    Fields absent from CBOE are set to None (greeks.py fills them in).

    CBOE now returns a flat list of contracts keyed by OCC symbol string
    rather than nested expiration blocks.
    """
    data = fetch_options_chain(cboe_ticker, refresh=refresh)
    raw = data.get("data", {})
    spot = raw.get("current_price", None)
    today = datetime.date.today()

    contracts = []
    for opt in raw.get("options", []):
        occ = opt.get("option", "")
        parsed = _parse_occ_symbol(occ)
        if parsed is None:
            continue
        expiry_str, call_put, strike = parsed

        dte = (datetime.date.fromisoformat(expiry_str) - today).days
        if dte < 0:
            continue

        bid = opt.get("bid", 0.0) or 0.0
        ask = opt.get("ask", 0.0) or 0.0
        mid = (bid + ask) / 2 if (bid + ask) > 0 else None
        spread_pct = ((ask - bid) / mid * 100) if (mid and mid > 0) else None

        contracts.append(
            {
                "ticker": cboe_ticker,
                "expiry": expiry_str,
                "dte": dte,
                "strike": strike,
                "type": call_put,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": opt.get("last_trade_price") or opt.get("last"),
                "volume": int(opt.get("volume", 0) or 0),
                "open_interest": int(opt.get("open_interest", 0) or 0),
                "iv": round((opt.get("iv") or opt.get("implied_volatility") or 0) * 100, 2) or None,
                "delta": opt.get("delta"),
                "gamma": opt.get("gamma"),
                "theta": opt.get("theta"),
                "vega": opt.get("vega"),
                "rho": opt.get("rho"),
                "theoretical": opt.get("theo") or opt.get("theoretical"),
                "spread_pct": spread_pct,
                "spot": spot,
            }
        )

    return contracts
