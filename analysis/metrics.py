"""
Descriptive per-contract and per-symbol metrics: VRP, IVR, IVP, ATM IV.

These describe where the option market currently sits. None of them is a
recommendation — the `trade_setup` classifier that emitted "sell_vol"/"buy_vol"
labels from hand-set thresholds was removed 2026-08-14.

IVR and IVP read their history from the append-only archive (data/archive.py),
not from a mutable cache table. They are only as good as that archive, which today
is thin — below 10 stored observations they return None rather than guessing.
"""

from data import archive


def vrp(iv_pct: float | None, hv30: float | None) -> float | None:
    """
    Volatility Risk Premium in vol points: IV - HV30 (both as %).
    Signed on purpose. Positive = options rich vs recent realized.
    """
    if iv_pct is None or hv30 is None:
        return None
    return round(iv_pct - hv30, 2)


MIN_IV_OBSERVATIONS = 10


def iv_rank(ticker: str, current_iv: float | None) -> float | None:
    """
    IV Rank (0-100): position of current IV within its trailing 52-week range.

    Range-based, so two outlier days set both endpoints and everything else is
    scored against them. Compare with iv_percentile, which uses the whole
    distribution — a wide gap between the two means the range is being set by
    a handful of days.
    """
    if current_iv is None:
        return None

    vals = [iv for _, iv in archive.iv30_series(ticker)]
    if len(vals) < MIN_IV_OBSERVATIONS:
        return None

    lo, hi = min(vals), max(vals)
    if hi == lo:
        return 50.0
    return round((current_iv - lo) / (hi - lo) * 100, 1)


def iv_percentile(ticker: str, current_iv: float | None) -> float | None:
    """
    IV Percentile (0-100): share of trailing-year observations below current IV.
    """
    if current_iv is None:
        return None

    vals = [iv for _, iv in archive.iv30_series(ticker)]
    if len(vals) < MIN_IV_OBSERVATIONS:
        return None

    below = sum(1 for v in vals if v < current_iv)
    return round(below / len(vals) * 100, 1)


def iv_history_depth(ticker: str) -> int:
    """How many archived observations back this symbol's IVR/IVP. Surfaced so the
    reader knows whether to believe them."""
    return len(archive.iv30_series(ticker))


def iv_divergence(ivr: float | None, ivp: float | None) -> float | None:
    """Gap between IV Rank and IV Percentile. Large gap means the range is being
    set by a few outlier days rather than the bulk of the distribution."""
    if ivr is None or ivp is None:
        return None
    return round(abs(ivr - ivp), 1)


def atm_iv(contracts: list[dict], spot: float | None) -> float | None:
    """
    Nearest-ATM front-month call IV, used as the representative "current IV"
    for the symbol.
    """
    if not spot:
        return None

    calls_with_iv = [
        c for c in contracts
        if c.get("type") == "C" and c.get("iv") is not None and c.get("dte", 0) > 0
    ]
    if not calls_with_iv:
        return None

    candidates = [c for c in calls_with_iv if 7 <= c.get("dte", 0) <= 60]
    if not candidates:
        candidates = calls_with_iv

    candidates.sort(key=lambda c: abs(c["strike"] - spot))
    return candidates[0].get("iv")


def enrich_contract(
    contract: dict,
    hv_data: dict,
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
    contract["iv_divergence"] = iv_divergence(ivr_val, ivp_val)
    return contract
