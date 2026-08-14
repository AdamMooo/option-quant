"""Offline smoke tests. No network calls."""

import math

import pytest

import main
from analysis import greeks as gk
from analysis import metrics as mx
from analysis import volatility as vol
from data import archive, demo


@pytest.fixture
def temp_archive(tmp_path, monkeypatch):
    """Point the archive at a throwaway DB so tests never touch the real one."""
    monkeypatch.setattr(archive, "DB_PATH", tmp_path / "chains.db")
    return archive


def _fake_raw(ticker="TEST", iv30=25.0):
    return {
        "timestamp": "2026-08-14T13:33:24",
        "symbol": ticker,
        "data": {
            "current_price": 100.0, "iv30": iv30,
            "open": 99.0, "high": 101.0, "low": 98.5, "close": 100.0,
            "prev_day_close": 99.5, "volume": 1_000_000,
            "bid": 99.99, "ask": 100.01, "last_trade_time": "2026-08-14T13:33:00",
        },
    }


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


def test_archive_round_trips_a_snapshot(temp_archive):
    contracts = demo.make_chain("TEST", spot=100.0)
    sid = temp_archive.write_snapshot("TEST", _fake_raw(), contracts)

    assert sid is not None
    rows = temp_archive.summary("TEST")
    assert rows[0]["snapshots"] == 1
    assert rows[0]["trading_days"] == 1
    # quote_date comes from the exchange timestamp, not from today's date
    assert rows[0]["first_date"] == "2026-08-14"


def test_archive_refuses_update_and_delete(temp_archive):
    contracts = demo.make_chain("TEST", spot=100.0)
    temp_archive.write_snapshot("TEST", _fake_raw(), contracts)

    conn = temp_archive._conn()
    for sql in (
        "UPDATE snapshots SET iv30 = 999",
        "DELETE FROM snapshots",
        "UPDATE contracts SET iv = 999",
        "DELETE FROM contracts",
    ):
        with pytest.raises(Exception, match="append-only"):
            conn.execute(sql)
    conn.close()


def test_second_capture_same_day_appends_rather_than_clobbers(temp_archive):
    """The failure mode of the old iv_history table: INSERT OR REPLACE on run date."""
    contracts = demo.make_chain("TEST", spot=100.0)
    temp_archive.write_snapshot("TEST", _fake_raw(iv30=25.0), contracts)
    temp_archive.write_snapshot("TEST", _fake_raw(iv30=31.0), contracts)

    rows = temp_archive.summary("TEST")
    assert rows[0]["snapshots"] == 2
    assert rows[0]["trading_days"] == 1

    # One observation per date for ranking purposes — the latest capture wins,
    # but the earlier one is still on disk.
    series = temp_archive.iv30_series("TEST", days=36500)
    assert len(series) == 1
    assert series[0][1] == 31.0


def test_iv_rank_returns_none_below_threshold(temp_archive):
    contracts = demo.make_chain("TEST", spot=100.0)
    temp_archive.write_snapshot("TEST", _fake_raw(), contracts)
    assert mx.iv_rank("TEST", 25.0) is None
    assert mx.iv_percentile("TEST", 25.0) is None
    assert mx.iv_history_depth("TEST") == 1
