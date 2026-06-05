"""
Composite 0–100 opportunity score for each contract.
Higher = more interesting for the trader to examine.
"""

from config import DTE_SWEET_MAX, DTE_SWEET_MIN, SCORING_WEIGHTS


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def _ivr_score(ivr: float | None) -> float:
    """IV Rank extremes are more interesting than a mid-range reading."""
    if ivr is None:
        return 50.0
    return _clamp(abs(ivr - 50.0) * 2)


def _ivp_score(ivp: float | None) -> float:
    """IV Percentile extremes are more interesting than the middle of the distribution."""
    if ivp is None:
        return 50.0
    return _clamp(abs(ivp - 50.0) * 2)


def _vrp_score(vrp: float | None) -> float:
    """Large VRP magnitude is the more interesting opportunity.
    Scale: 0 → 0, ±10 → 50, ±20 → 100.
    """
    if vrp is None:
        return 50.0
    return _clamp(abs(vrp) * 5)


def _gamma_score(gamma: float | None) -> float:
    """Normalize gamma into 0–100. Reference range: 0–0.10 for typical equity options."""
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
    """Peak score in the 21–45 DTE sweet spot; tapers off on either side."""
    if dte is None:
        return 0.0
    if DTE_SWEET_MIN <= dte <= DTE_SWEET_MAX:
        return 100.0
    if dte < DTE_SWEET_MIN:
        return _clamp(dte / DTE_SWEET_MIN * 100)
    # dte > DTE_SWEET_MAX — decay linearly to 0 at 180d
    return _clamp(100 - (dte - DTE_SWEET_MAX) / (180 - DTE_SWEET_MAX) * 100)


def _ma_alignment_score(price: float | None, ma20: float | None, ma50: float | None, ma200: float | None, opt_type: str) -> float:
    """
    Score based on how many MAs the price is above (bullish) or below (bearish).
    Calls: price above MAs = high score. Puts: price below MAs = high score.
    """
    if price is None:
        return 50.0
    mas = [ma for ma in (ma20, ma50, ma200) if ma is not None]
    if not mas:
        return 50.0
    bullish_count = sum(1 for ma in mas if price > ma)
    bear_count = len(mas) - bullish_count
    if opt_type == "C":
        return _clamp(bullish_count / len(mas) * 100)
    else:
        return _clamp(bear_count / len(mas) * 100)


def _rsi_score(rsi: float | None, opt_type: str) -> float:
    """
    Calls score high when RSI < 40 (oversold, bounce potential).
    Puts score high when RSI > 60 (overbought, mean-revert potential).
    Neutral zone (40-60) scores ~50 for both.
    """
    if rsi is None:
        return 50.0
    if opt_type == "C":
        if rsi <= 30:
            return 100.0
        if rsi <= 40:
            return _clamp(100 - (rsi - 30) * 5)
        if rsi <= 60:
            return 50.0
        # Calls lose score as RSI gets overbought
        return _clamp(50 - (rsi - 60) * 2.5)
    else:
        if rsi >= 70:
            return 100.0
        if rsi >= 60:
            return _clamp(100 - (70 - rsi) * 5)
        if rsi >= 40:
            return 50.0
        return _clamp(50 - (40 - rsi) * 2.5)


def _momentum_confluence_score(mom20: float | None, mom60: float | None, opt_type: str) -> float:
    """
    Both timeframes agree and point the right direction = high score.
    Disagreement = penalized. Magnitude matters.
    """
    if mom20 is None and mom60 is None:
        return 50.0
    # Use available signals
    signals = [m for m in (mom20, mom60) if m is not None]
    if opt_type == "P":
        signals = [-s for s in signals]
    avg = sum(signals) / len(signals)
    # Confluence bonus: both same direction
    if len(signals) == 2 and (signals[0] > 0) == (signals[1] > 0):
        multiplier = 1.2
    else:
        multiplier = 0.7
    return _clamp(50 + avg * 500 * multiplier)


def _rs_score(rs20: float | None, opt_type: str) -> float:
    """
    Relative strength vs SPY over 20 days.
    Calls: outperforming SPY = good. Puts: underperforming = good.
    +/-5% RS maps roughly to 0-100.
    """
    if rs20 is None:
        return 50.0
    signed = rs20 if opt_type == "C" else -rs20
    return _clamp(50 + signed * 1000)


def _earnings_score(days_to_earnings: int | None) -> float:
    """
    Penalize hard when earnings are imminent — direction thesis gets overwhelmed by event risk.
    < 7 days: 0 (don't trade direction into earnings)
    7-14 days: heavy penalty
    14-21 days: moderate penalty
    > 21 days: no penalty (full score)
    """
    if days_to_earnings is None:
        return 75.0  # unknown: slight discount vs confirmed-clear
    if days_to_earnings < 7:
        return 0.0
    if days_to_earnings < 14:
        return _clamp((days_to_earnings - 7) / 7 * 40)
    if days_to_earnings < 21:
        return _clamp(40 + (days_to_earnings - 14) / 7 * 35)
    return 100.0


def quality_score(c: dict) -> float:
    """Weighted quality score from IV/VRP/liquidity/gamma/DTE metrics."""
    w = SCORING_WEIGHTS
    return round(
        w["ivr"] * _ivr_score(c.get("ivr"))
        + w["ivp"] * _ivp_score(c.get("ivp"))
        + w["vrp"] * _vrp_score(c.get("vrp"))
        + w["gamma"] * _gamma_score(c.get("gamma"))
        + w["liquidity"] * _liquidity_score(c.get("spread_pct"), c.get("open_interest"))
        + w["dte"] * _dte_score(c.get("dte"))
        , 1
    )


def direction_score(c: dict) -> float:
    """
    Multi-factor directional alignment score (0-100).
    Weights: MA alignment 25%, RSI 20%, momentum confluence 20%, RS vs SPY 20%, earnings 15%.
    A contract only scores high when multiple independent factors agree.
    """
    opt_type = c.get("type", "C")
    price = c.get("price") or c.get("spot")

    ma = _ma_alignment_score(price, c.get("ma20"), c.get("ma50"), c.get("ma200"), opt_type)
    rsi = _rsi_score(c.get("rsi14"), opt_type)
    mom = _momentum_confluence_score(c.get("mom20"), c.get("mom60"), opt_type)
    rs = _rs_score(c.get("rs20"), opt_type)
    earn = _earnings_score(c.get("days_to_earnings"))

    score = ma * 0.25 + rsi * 0.20 + mom * 0.20 + rs * 0.20 + earn * 0.15
    return round(score, 1)


def score_contract(c: dict) -> float:
    """Returns composite score 0–100 for a single contract dict."""
    q = quality_score(c)
    d = direction_score(c)
    total = round(q * 0.80 + d * 0.20, 1)
    c["quality_score"] = q
    c["direction_score"] = d
    return total


def score_all(contracts: list[dict]) -> list[dict]:
    """Attach 'score' field to each contract and return sorted descending."""
    for c in contracts:
        c["score"] = score_contract(c)
    return sorted(contracts, key=lambda c: c["score"], reverse=True)
