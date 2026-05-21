"""
Generates synthetic but realistic options chain data for offline testing.
Used via `python main.py --demo`.
"""

import datetime
import math
import random

from analysis.greeks import compute_greeks, bs_price
from config import RISK_FREE_RATE


def make_chain(
    cboe_ticker: str,
    spot: float = 100.0,
    hv30: float = 18.0,
    iv_premium: float = 2.0,
    seed: int | None = None,
) -> list[dict]:
    """
    Returns a synthetic options chain for `cboe_ticker` around `spot`.
    iv_premium: extra vol (pp) added to HV to simulate VRP.
    """
    rng = random.Random(seed or hash(cboe_ticker) % 2**31)
    today = datetime.date.today()
    sigma = (hv30 + iv_premium) / 100  # fractional

    expirations = [
        today + datetime.timedelta(days=d)
        for d in (14, 21, 35, 49, 63, 91, 126)
    ]
    strikes_pct = [0.80, 0.85, 0.90, 0.95, 0.975, 1.0, 1.025, 1.05, 1.10, 1.15, 1.20]

    contracts = []
    for expiry in expirations:
        dte = (expiry - today).days
        T = dte / 365.0
        for pct in strikes_pct:
            K = round(spot * pct, 1)
            for opt_type in ("C", "P"):
                theo = bs_price(spot, K, T, RISK_FREE_RATE, sigma, opt_type)
                if theo < 0.01:
                    continue

                spread = max(0.05, theo * rng.uniform(0.01, 0.06))
                bid = round(theo - spread / 2, 2)
                ask = round(theo + spread / 2, 2)
                mid = (bid + ask) / 2

                iv_val = (sigma + rng.uniform(-0.01, 0.01)) * 100

                greeks = compute_greeks(spot, K, T, RISK_FREE_RATE, sigma, opt_type)

                oi = int(abs(rng.gauss(800, 400)))
                volume = int(oi * rng.uniform(0.05, 0.3))
                spread_pct = (ask - bid) / mid * 100 if mid > 0 else None

                contracts.append({
                    "ticker": cboe_ticker,
                    "expiry": expiry.isoformat(),
                    "dte": dte,
                    "strike": K,
                    "type": opt_type,
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "last": round(mid * rng.uniform(0.97, 1.03), 2),
                    "volume": volume,
                    "open_interest": oi,
                    "iv": round(iv_val, 2),
                    "delta": greeks["delta"],
                    "gamma": greeks["gamma"],
                    "theta": greeks["theta"],
                    "vega": greeks["vega"],
                    "rho": greeks["rho"],
                    "theoretical": round(theo, 2),
                    "spread_pct": round(spread_pct, 2) if spread_pct else None,
                    "spot": spot,
                })
    return contracts


def make_price_history(spot: float, hv30: float = 18.0, days: int = 380, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    sigma_daily = hv30 / 100 / math.sqrt(252)
    prices = [spot]
    for _ in range(days - 1):
        prices.insert(0, prices[0] * math.exp(rng.gauss(-sigma_daily**2 / 2, sigma_daily)))

    start = datetime.date.today() - datetime.timedelta(days=days - 1)
    return [
        {"date": (start + datetime.timedelta(days=i)).isoformat(), "close": p}
        for i, p in enumerate(prices)
    ]


# Demo universe: a representative subset of TSX 60 names
DEMO_SYMBOLS = {
    "RY":   {"spot": 141.20, "hv30": 16.5, "iv_premium": 1.8},
    "TD":   {"spot":  71.80, "hv30": 17.2, "iv_premium": 2.1},
    "BNS":  {"spot":  58.40, "hv30": 18.9, "iv_premium": 1.5},
    "CNI":  {"spot": 121.50, "hv30": 15.8, "iv_premium": 3.2},
    "CP":   {"spot":  83.10, "hv30": 16.4, "iv_premium": 2.9},
    "ENB":  {"spot":  44.30, "hv30": 14.2, "iv_premium": 1.2},
    "SU":   {"spot":  52.70, "hv30": 22.1, "iv_premium": 2.7},
    "SHOP": {"spot":  84.90, "hv30": 42.3, "iv_premium": 5.1},
    "GOLD": {"spot":  19.80, "hv30": 28.7, "iv_premium": 3.8},
    "CCJ":  {"spot":  48.60, "hv30": 33.2, "iv_premium": 4.5},
}
