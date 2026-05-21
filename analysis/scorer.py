"""
Composite 0–100 opportunity score for each contract.
Higher = more interesting for the trader to examine.
"""

from config import DTE_SWEET_MAX, DTE_SWEET_MIN, SCORING_WEIGHTS


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def _ivr_score(ivr: float | None) -> float:
    """Low IVR = cheap options = higher score for buyers."""
    if ivr is None:
        return 50.0
    return _clamp(100 - ivr)  # IVR 0 → score 100, IVR 100 → score 0


def _vrp_score(vrp: float | None) -> float:
    """
    VRP centered around 0. Negative VRP (options cheap vs realized) scores higher.
    Scale: ±10 pp maps to 0–100.
    """
    if vrp is None:
        return 50.0
    return _clamp(50 - vrp * 5)


def _gamma_score(gamma: float | None) -> float:
    """
    Normalize gamma into 0–100.  Reference range: 0–0.10 for typical equity options.
    """
    if gamma is None:
        return 0.0
    return _clamp(gamma * 1000)


def _liquidity_score(spread_pct: float | None, open_interest: int | None) -> float:
    """Tight spread and high OI = good liquidity."""
    spread_sub = 50.0
    oi_sub = 50.0

    if spread_pct is not None:
        # 0% spread → 100, 15% spread → 0
        spread_sub = _clamp(100 - spread_pct * (100 / 15))

    if open_interest is not None:
        # OI 0 → 0, OI 1000+ → 100 (logarithmic feel via sqrt)
        oi_sub = _clamp((open_interest**0.5) / 31.6 * 100)

    return (spread_sub + oi_sub) / 2


def _dte_score(dte: int | None) -> float:
    """
    Peak score in the 21–45 DTE sweet spot; tapers off on either side.
    """
    if dte is None:
        return 0.0
    if DTE_SWEET_MIN <= dte <= DTE_SWEET_MAX:
        return 100.0
    if dte < DTE_SWEET_MIN:
        return _clamp(dte / DTE_SWEET_MIN * 100)
    # dte > DTE_SWEET_MAX — decay linearly to 0 at 180d
    return _clamp(100 - (dte - DTE_SWEET_MAX) / (180 - DTE_SWEET_MAX) * 100)


def _momentum_score(mom20: float | None, opt_type: str) -> float:
    """
    Positive momentum → higher score for calls; negative → higher for puts.
    Scale: ±10% return maps to 0–100.
    """
    if mom20 is None:
        return 50.0
    signed = mom20 if opt_type == "C" else -mom20
    return _clamp(50 + signed * 500)


def score_contract(c: dict) -> float:
    """Returns composite score 0–100 for a single contract dict."""
    w = SCORING_WEIGHTS
    s = (
        w["ivr"] * _ivr_score(c.get("ivr"))
        + w["vrp"] * _vrp_score(c.get("vrp"))
        + w["gamma"] * _gamma_score(c.get("gamma"))
        + w["liquidity"] * _liquidity_score(c.get("spread_pct"), c.get("open_interest"))
        + w["dte"] * _dte_score(c.get("dte"))
        + w["momentum"] * _momentum_score(c.get("mom20"), c.get("type", "C"))
    )
    return round(s, 1)


def score_all(contracts: list[dict]) -> list[dict]:
    """Attach 'score' field to each contract and return sorted descending."""
    for c in contracts:
        c["score"] = score_contract(c)
    return sorted(contracts, key=lambda c: c["score"], reverse=True)
