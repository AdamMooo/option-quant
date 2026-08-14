"""Offline smoke tests. No network calls."""

import math

import pytest

import main
from analysis import greeks as gk
from analysis import metrics as mx
from analysis import volatility as vol
from data import demo


def test_demo_pipeline_produces_enriched_contracts():
    contracts, ctx = main.process_demo_symbol("SHOP")

    assert contracts
    assert ctx["spot"] > 0
    assert ctx["atm_iv"] is not None
    assert ctx["hv"]["hv30"] is not None
    # IVR/IVP need stored history, which demo mode does not have.
    assert ctx["ivr"] is None and ctx["ivp"] is None

    c = contracts[0]
    for field in ("iv", "delta", "gamma", "theta", "vega", "vrp", "hv30"):
        assert field in c


def test_vrp_is_signed():
    assert mx.vrp(25.0, 18.0) == 7.0
    assert mx.vrp(15.0, 18.0) == -3.0
    assert mx.vrp(None, 18.0) is None


def test_implied_vol_round_trips():
    S, K, T, r, sigma = 100.0, 105.0, 0.25, 0.05, 0.32
    price = gk.bs_price(S, K, T, r, sigma, "C")
    recovered = gk.implied_vol(price, S, K, T, r, "C")
    assert recovered == pytest.approx(sigma, abs=1e-4)


def test_put_call_parity():
    S, K, T, r, sigma = 100.0, 95.0, 0.5, 0.05, 0.28
    call = gk.bs_price(S, K, T, r, sigma, "C")
    put = gk.bs_price(S, K, T, r, sigma, "P")
    assert (call - put) == pytest.approx(S - K * math.exp(-r * T), abs=1e-6)


def test_realized_vol_recovers_known_sigma():
    history = demo.make_price_history(spot=100.0, hv30=25.0, days=400)
    hv = vol.compute_hv(history)
    # Sampling noise on 60 observations is wide; assert the right neighbourhood.
    assert 15.0 < hv["hv60"] < 40.0


def test_filters_narrow_the_chain():
    contracts, _ = main.process_demo_symbol("RY")
    calls = main.apply_filters(
        contracts, opt_type="C", moneyness="otm",
        dte_min=21, dte_max=60, min_oi=0, sort_by="chain",
    )
    assert calls
    assert all(c["type"] == "C" for c in calls)
    assert all(c["strike"] > c["spot"] for c in calls)
    assert all(21 <= c["dte"] <= 60 for c in calls)
    # chain sort is (dte, type, strike)
    keys = [(c["dte"], c["type"], c["strike"]) for c in calls]
    assert keys == sorted(keys)
