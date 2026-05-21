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
