"""Realized volatility from daily price history.

Direction inference (moving averages, RSI, relative strength, momentum) was removed
2026-08-14 — the user supplies the thesis. See options-quant.md.
"""

import math

import numpy as np
import pandas as pd


def compute_hv(price_records: list[dict], windows: list[int] = (10, 20, 30, 60)) -> dict[str, float | None]:
    """
    Returns annualized realized vol for each window, as a percentage (e.g. 18.4 = 18.4%).
    price_records: list of {date, close} dicts, chronological.
    Returns None for a window if insufficient data.

    Note: closes come from yfinance with auto_adjust=True, so they are retroactively
    dividend-adjusted. Fine for a current-state read; NOT point-in-time valid. Do not
    use this for anything claiming to be observable-at-the-time.
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
            result[key] = round(std * math.sqrt(252) * 100, 2)
    return result


def largest_move(price_records: list[dict], window: int = 30) -> dict | None:
    """
    Biggest single-day log return in the trailing window, and what realized vol
    would be without it.

    Close-to-close realized vol has a fat-tailed sampling distribution and is badly
    non-robust to jumps: one earnings gap in a 30-day window can move the annualized
    number by 8+ vol points. Since that number is about to be compared against a
    forward-looking implied vol whose window may contain no such event, the reader
    needs to see it. The literature fix is a jump-robust estimator (bipower
    variation, Barndorff-Nielsen & Shephard 2004) — not built yet.
    """
    if len(price_records) < window + 1:
        return None

    closes = pd.Series([r["close"] for r in price_records])
    dates = [r["date"] for r in price_records]
    log_returns = np.log(closes / closes.shift(1)).dropna()
    recent = log_returns.iloc[-window:]
    if len(recent) < 3:
        return None

    idx = int(recent.abs().idxmax())
    biggest = float(recent.loc[idx])
    ex = recent.drop(index=idx)

    return {
        "date": dates[idx],
        "move_pct": round(biggest * 100, 2),
        "hv_ex_jump": round(float(ex.std(ddof=1)) * math.sqrt(252) * 100, 2),
    }
