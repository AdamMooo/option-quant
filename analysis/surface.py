"""
The implied volatility surface for one name, on one day.

Two descriptive cuts, both self-contained facts about the current chain — neither
needs archive history and neither compares this name to any other:

  Term structure — ATM implied vol as a function of expiry. Answers "is the front
  month bid relative to the back, and where is the earnings kink."

  Skew — implied vol as a function of delta, within an expiry. Answers "what is
  the market paying for downside versus upside."

Both are quoted in vol points (22.4 = 22.4%), matching the rest of the repo.

Nothing here ranks, scores, or recommends. See options-quant.md.
"""

# Standard market convention. 25-delta is far enough out to carry the wing
# information and near enough in to still be liquid on most names.
TARGET_DELTA = 0.25


def _usable(c: dict) -> bool:
    """
    A contract whose IV means something.

    Requires a live two-sided market: a contract with no bid has no price to
    invert, and its "mid" is half the ask, which produces an IV that is an
    artifact of the quote convention rather than an observation about vol.
    """
    return (
        c.get("iv") is not None
        and c["iv"] > 0
        and c.get("delta") is not None
        and (c.get("bid") or 0) > 0
        and (c.get("ask") or 0) > 0
        # Expiring today has no time value left to invert; its "IV" is an
        # artifact of the last few cents of price, not a vol observation.
        and (c.get("dte") or 0) > 0
    )


def _interp(x: float, x0: float, y0: float, x1: float, y1: float) -> float:
    """Linear interpolation. Guards the degenerate x0 == x1 case."""
    if x1 == x0:
        return (y0 + y1) / 2
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _iv_at_strike(contracts: list[dict], spot: float) -> float | None:
    """
    IV interpolated to strike == spot, from one option type in one expiry.

    Interpolating rather than taking the nearest strike matters: with strikes on
    a 2.50 grid, "nearest" makes the ATM series step as spot drifts across the
    grid, which reads as vol moving when only the tape moved.

    Returns None rather than extrapolating if spot is outside the listed strikes.
    """
    pts = sorted({(c["strike"], c["iv"]) for c in contracts})
    if len(pts) < 2:
        return None

    for (k_lo, iv_lo), (k_hi, iv_hi) in zip(pts, pts[1:]):
        if k_lo <= spot <= k_hi:
            return _interp(spot, k_lo, iv_lo, k_hi, iv_hi)
    return None


def _iv_at_delta(contracts: list[dict], target: float) -> float | None:
    """
    IV interpolated to |delta| == target, from one option type in one expiry.

    Delta is used as the moneyness coordinate because it normalises for both
    tenor and vol level — a 25-delta option is about the same distance out in
    standard deviations whether it expires in a week or a year, which a fixed
    strike offset is not.

    Calls carry delta in (0, 1) and puts in (-1, 0), so both are mapped through
    |delta|; on both sides 0.25 is out of the money.

    Returns None rather than extrapolating if the chain does not bracket the
    target — a thin chain should say "unknown", not invent a wing.
    """
    pts = sorted({(abs(c["delta"]), c["iv"]) for c in contracts})
    if len(pts) < 2:
        return None

    for (d_lo, iv_lo), (d_hi, iv_hi) in zip(pts, pts[1:]):
        if d_lo <= target <= d_hi:
            return _interp(target, d_lo, iv_lo, d_hi, iv_hi)
    return None


def surface_by_expiry(
    contracts: list[dict],
    spot: float | None,
    target_delta: float = TARGET_DELTA,
) -> list[dict]:
    """
    One row per expiry: ATM IV, the 25-delta wings, and the two standard
    summaries of smile shape.

        risk_reversal = IV(25d put) - IV(25d call)
            Positive: puts bid over calls — the market is paying up for
            downside. The usual state for equity index and most single names.

        butterfly = mean(IV(25d put), IV(25d call)) - IV(ATM)
            Positive: wings rich relative to the body — tails priced fatter
            than a lognormal would imply.

    Fields are None where the chain does not support them. A missing wing is
    reported as missing.
    """
    if not spot or spot <= 0:
        return []

    by_expiry: dict[str, list[dict]] = {}
    for c in contracts:
        if _usable(c):
            by_expiry.setdefault(c["expiry"], []).append(c)

    rows = []
    for expiry, group in by_expiry.items():
        calls = [c for c in group if c.get("type") == "C"]
        puts = [c for c in group if c.get("type") == "P"]

        atm_call = _iv_at_strike(calls, spot)
        atm_put = _iv_at_strike(puts, spot)
        # Put-call parity forces same-strike IVs to agree in theory; the observed
        # gap is the forward (rates, dividends, borrow) plus bid-ask. Averaging
        # both sides cancels most of it. Fall back to whichever side exists.
        pair = [v for v in (atm_call, atm_put) if v is not None]
        atm = sum(pair) / len(pair) if pair else None

        put25 = _iv_at_delta(puts, target_delta)
        call25 = _iv_at_delta(calls, target_delta)

        rr = put25 - call25 if (put25 is not None and call25 is not None) else None
        bf = (
            (put25 + call25) / 2 - atm
            if (put25 is not None and call25 is not None and atm is not None)
            else None
        )

        rows.append({
            "expiry": expiry,
            "dte": group[0].get("dte"),
            "atm_iv": atm,
            "put25_iv": put25,
            "call25_iv": call25,
            "risk_reversal": rr,
            "butterfly": bf,
            "n_strikes": len({c["strike"] for c in group}),
        })

    return sorted(rows, key=lambda r: r["dte"] if r["dte"] is not None else 0)


def term_slope(rows: list[dict], near_dte: int = 30, far_dte: int = 90) -> dict | None:
    """
    ATM IV at two points on the curve, and the gap between them.

    Interpolated in DTE across expiries so the number does not jump each time an
    expiry rolls off — the same reason ATM IV is interpolated across strikes.

    Positive slope (far above near) is the usual state: contango, the market
    charging more for longer-dated uncertainty. Negative means the front is bid
    over the back, which is what an imminent event looks like.
    """
    pts = sorted(
        (r["dte"], r["atm_iv"]) for r in rows
        if r["atm_iv"] is not None and r["dte"] is not None
    )
    if len(pts) < 2:
        return None

    def at(dte: int) -> float | None:
        if dte < pts[0][0] or dte > pts[-1][0]:
            return None
        for (d_lo, iv_lo), (d_hi, iv_hi) in zip(pts, pts[1:]):
            if d_lo <= dte <= d_hi:
                return _interp(dte, d_lo, iv_lo, d_hi, iv_hi)
        return None

    near, far = at(near_dte), at(far_dte)
    if near is None or far is None:
        return None

    return {
        "near_dte": near_dte,
        "far_dte": far_dte,
        "near_iv": near,
        "far_iv": far,
        "slope": far - near,
    }
