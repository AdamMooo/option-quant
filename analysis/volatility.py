"""Historical volatility calculation from daily price history."""

import math

import numpy as np
import pandas as pd


def compute_hv(price_records: list[dict], windows: list[int] = (10, 20, 30, 60)) -> dict[str, float | None]:
    """
    Returns annualized HV for each window (e.g. HV10, HV20, HV30, HV60).
    price_records: list of {date, close} dicts, chronological.
    Returns None for a window if insufficient data.
    """
    if len(price_records) < 2:
        return {f"hv{w}": None for w in windows}

    closes = pd.Series(
        [r["close"] for r in price_records],
        index=pd.to_datetime([r["date"] for r in price_records]),
    )
    log_returns = np.log(closes / closes.shift(1)).dropna()

    result = {}
    for w in windows:
        key = f"hv{w}"
        if len(log_returns) < w:
            result[key] = None
        else:
            std = float(log_returns.iloc[-w:].std(ddof=1))
            result[key] = round(std * math.sqrt(252) * 100, 2)  # as percentage
    return result


def momentum(price_records: list[dict], days: int) -> float | None:
    """
    Price return over the last `days` trading days (as a decimal, e.g. 0.05 = +5%).
    """
    closes = [r["close"] for r in price_records]
    if len(closes) < days + 1:
        return None
    return (closes[-1] / closes[-(days + 1)]) - 1


def compute_technicals(price_records: list[dict], spy_records: list[dict] | None = None) -> dict:
    """
    Compute technical indicators from price history.
    Returns dict with: ma20, ma50, ma200, rsi14, rs20 (vs SPY), hv_trend.
    All values may be None if insufficient data.
    """
    if not price_records:
        return {}

    closes = pd.Series([r["close"] for r in price_records])
    result: dict = {}

    # Moving average alignment
    for w, key in [(20, "ma20"), (50, "ma50"), (200, "ma200")]:
        if len(closes) >= w:
            result[key] = float(closes.iloc[-w:].mean())
        else:
            result[key] = None

    result["price"] = float(closes.iloc[-1])

    # RSI(14)
    if len(closes) >= 15:
        delta = closes.diff().dropna()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.iloc[-14:].mean()
        avg_loss = loss.iloc[-14:].mean()
        if avg_loss == 0:
            result["rsi14"] = 100.0
        else:
            rs = avg_gain / avg_loss
            result["rsi14"] = round(float(100 - 100 / (1 + rs)), 1)
    else:
        result["rsi14"] = None

    # Relative strength vs SPY over 20 days
    if spy_records and len(closes) >= 21:
        spy_closes = pd.Series([r["close"] for r in spy_records])
        if len(spy_closes) >= 21:
            stock_ret = closes.iloc[-1] / closes.iloc[-21] - 1
            spy_ret = spy_closes.iloc[-1] / spy_closes.iloc[-21] - 1
            result["rs20"] = round(float(stock_ret - spy_ret), 4)
        else:
            result["rs20"] = None
    else:
        result["rs20"] = None

    # HV trend: HV10 vs HV30 — positive means vol expanding
    hv = compute_hv(price_records)
    hv10 = hv.get("hv10")
    hv30 = hv.get("hv30")
    result["hv_trend"] = round(hv10 - hv30, 2) if (hv10 and hv30) else None

    return result
