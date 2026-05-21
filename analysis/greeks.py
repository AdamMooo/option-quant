"""
Black-Scholes IV inversion and Greeks.
Used as fallback when CBOE doesn't supply IV/Greeks for a contract.
"""

import math

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


def _d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
    return (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))


def _d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
    return _d1(S, K, T, r, sigma) - sigma * math.sqrt(T)


def bs_price(S: float, K: float, T: float, r: float, sigma: float, opt_type: str) -> float:
    """Black-Scholes theoretical price."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = _d1(S, K, T, r, sigma)
    d2 = _d2(S, K, T, r, sigma)
    if opt_type == "C":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def implied_vol(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    opt_type: str,
) -> float | None:
    """
    Newton-Raphson / Brent inversion for IV.
    Returns IV as a decimal (e.g. 0.20 = 20%), or None if inversion fails.
    """
    if market_price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return None

    intrinsic = max(0.0, (S - K) if opt_type == "C" else (K - S))
    if market_price <= intrinsic:
        return None

    try:
        iv = brentq(
            lambda sigma: bs_price(S, K, T, r, sigma, opt_type) - market_price,
            1e-6,
            20.0,
            xtol=1e-6,
            maxiter=100,
        )
        return iv
    except (ValueError, RuntimeError):
        return None


def compute_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    opt_type: str,
) -> dict[str, float]:
    """
    Returns delta, gamma, theta (per calendar day), vega (per 1% move), rho.
    All values as floats; zero if T <= 0 or sigma <= 0.
    """
    if T <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    d1 = _d1(S, K, T, r, sigma)
    d2 = _d2(S, K, T, r, sigma)
    pdf_d1 = norm.pdf(d1)
    sqrt_T = math.sqrt(T)

    gamma = pdf_d1 / (S * sigma * sqrt_T)
    vega = S * pdf_d1 * sqrt_T / 100  # per 1% vol move

    if opt_type == "C":
        delta = norm.cdf(d1)
        theta = (
            -(S * pdf_d1 * sigma) / (2 * sqrt_T)
            - r * K * math.exp(-r * T) * norm.cdf(d2)
        ) / 365
        rho = K * T * math.exp(-r * T) * norm.cdf(d2) / 100
    else:
        delta = norm.cdf(d1) - 1
        theta = (
            -(S * pdf_d1 * sigma) / (2 * sqrt_T)
            + r * K * math.exp(-r * T) * norm.cdf(-d2)
        ) / 365
        rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 5),
        "theta": round(theta, 4),
        "vega": round(vega, 4),
        "rho": round(rho, 4),
    }


def fill_greeks(contract: dict, r: float) -> dict:
    """
    In-place enrichment: if IV or Greeks are missing from a contract dict,
    compute them from Black-Scholes. Returns the modified dict.
    """
    S = contract.get("spot") or 0
    K = contract.get("strike") or 0
    dte = contract.get("dte") or 0
    opt_type = contract.get("type", "C")
    mid = contract.get("mid")
    T = dte / 365.0

    if S <= 0 or K <= 0 or T <= 0:
        return contract

    # Fill IV if missing
    if contract.get("iv") is None and mid and mid > 0:
        iv = implied_vol(mid, S, K, T, r, opt_type)
        contract["iv"] = round(iv * 100, 2) if iv else None  # store as %

    sigma = (contract.get("iv") or 0) / 100  # back to decimal

    # Fill Greeks if missing
    if sigma > 0 and contract.get("delta") is None:
        greeks = compute_greeks(S, K, T, r, sigma, opt_type)
        for key, val in greeks.items():
            if contract.get(key) is None:
                contract[key] = val

    return contract
