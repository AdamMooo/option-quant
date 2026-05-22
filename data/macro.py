"""
Macro conditions via FRED API.
Fetches VIX, VIX3M, 10Y yield, and Fed Funds rate.
Falls back to no-key CSV endpoint if FRED_API_KEY is not set.
"""

import os
import datetime
import requests

from data import cache

_FRED_API_KEY = os.getenv("FRED_API_KEY", "")
_CACHE_TTL = 4 * 60 * 60  # 4 hours — macro data is daily anyway

_SERIES = {
    "vix":       "VIXCLS",   # CBOE VIX
    "vix3m":     "VXVCLS",   # VIX 3-month (term structure)
    "yield_10y": "DGS10",    # 10-year Treasury yield
    "fed_funds":  "DFF",      # Fed Funds effective rate
}


def _fetch_series(series_id: str) -> float | None:
    """Fetch the latest value for a FRED series. Returns None on failure."""
    cached = cache.get_macro(series_id, _CACHE_TTL)
    if cached is not None:
        return cached

    try:
        if _FRED_API_KEY:
            url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={_FRED_API_KEY}"
                f"&file_type=json&sort_order=desc&limit=5"
            )
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            obs = r.json().get("observations", [])
            for o in obs:
                if o.get("value") not in (".", ""):
                    value = float(o["value"])
                    cache.set_macro(series_id, value)
                    return value
        else:
            # No-key CSV fallback
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            lines = [l for l in r.text.strip().splitlines() if not l.startswith("DATE") and "." in l]
            if lines:
                value = float(lines[-1].split(",")[1])
                cache.set_macro(series_id, value)
                return value
    except Exception:
        pass
    return None


def fetch_macro() -> dict:
    """
    Returns dict with keys: vix, vix3m, yield_10y, fed_funds.
    Any unavailable series will be None.
    """
    return {key: _fetch_series(sid) for key, sid in _SERIES.items()}


def vix_regime(vix: float | None) -> str:
    """Human-readable VIX regime label."""
    if vix is None:
        return "unknown"
    if vix < 15:
        return "low"
    if vix < 20:
        return "normal"
    if vix < 30:
        return "elevated"
    return "high"


def term_structure(vix: float | None, vix3m: float | None) -> str:
    """Contango = market calm, backwardation = near-term fear."""
    if vix is None or vix3m is None:
        return "unknown"
    if vix < vix3m:
        return "contango"
    return "backwardation"
