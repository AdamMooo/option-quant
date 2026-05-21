"""
Per-contract and per-symbol metrics: VRP, IVR, IVP, momentum, etc.
"""

import datetime

from data import cache


def vrp(iv_pct: float | None, hv30: float | None) -> float | None:
    """Volatility Risk Premium: IV - HV30 (both as %).  Positive = options expensive."""
    if iv_pct is None or hv30 is None:
        return None
    return round(iv_pct - hv30, 2)


def iv_rank(ticker: str, current_iv: float | None) -> float | None:
    """
    IV Rank (0–100): position of current IV within its 52-week range.
    Uses iv_history table in SQLite.
    """
    if current_iv is None:
        return None

    rows = cache.get_iv_history(ticker)
    if len(rows) < 10:
        return None

    cutoff = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    vals = [iv for date, iv in rows if date >= cutoff]
    if not vals:
        return None

    lo, hi = min(vals), max(vals)
    if hi == lo:
        return 50.0
    return round((current_iv - lo) / (hi - lo) * 100, 1)


def iv_percentile(ticker: str, current_iv: float | None) -> float | None:
    """
    IV Percentile (0–100): % of past 252 trading days where IV was below current IV.
    """
    if current_iv is None:
        return None

    rows = cache.get_iv_history(ticker)
    if len(rows) < 10:
        return None

    cutoff = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    vals = [iv for date, iv in rows if date >= cutoff]
    if not vals:
        return None

    below = sum(1 for v in vals if v < current_iv)
    return round(below / len(vals) * 100, 1)


def update_iv_history(ticker: str, iv: float | None) -> None:
    """Saves today's IV to history for future IVR / IVP calculations."""
    if iv is None:
        return
    today = datetime.date.today().isoformat()
    cache.upsert_iv_history(ticker, today, iv)


def atm_iv(contracts: list[dict], spot: float | None) -> float | None:
    """
    Finds the nearest-ATM call with a valid IV and returns it.
    Used as the representative "current IV" for a symbol.
    """
    if not spot:
        return None

    calls_with_iv = [
        c for c in contracts
        if c.get("type") == "C" and c.get("iv") is not None and c.get("dte", 0) > 0
    ]
    if not calls_with_iv:
        return None

    # Pick front-month dte range (7–60 days), closest to ATM
    candidates = [c for c in calls_with_iv if 7 <= c.get("dte", 0) <= 60]
    if not candidates:
        candidates = calls_with_iv

    candidates.sort(key=lambda c: abs(c["strike"] - spot))
    return candidates[0].get("iv")


def enrich_contract(
    contract: dict,
    hv_data: dict,
    mom20: float | None,
    mom60: float | None,
    ivr_val: float | None,
    ivp_val: float | None,
) -> dict:
    """Attaches derived metrics to a contract dict."""
    iv = contract.get("iv")
    contract["hv10"] = hv_data.get("hv10")
    contract["hv20"] = hv_data.get("hv20")
    contract["hv30"] = hv_data.get("hv30")
    contract["hv60"] = hv_data.get("hv60")
    contract["vrp"] = vrp(iv, hv_data.get("hv30"))
    contract["ivr"] = ivr_val
    contract["ivp"] = ivp_val
    contract["mom20"] = round(mom20 * 100, 2) if mom20 is not None else None
    contract["mom60"] = round(mom60 * 100, 2) if mom60 is not None else None
    return contract
