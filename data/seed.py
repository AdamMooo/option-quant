"""
Seed list for archive capture.

This is a **seed, not a membership list.** It is read once, by
`archive.py capture --seed`, to enrol tickers into the archive. After that the
archive itself is the source of truth and the daily job runs `--from-archive`.

That distinction is what keeps this from becoming a stale table. Index membership
drifts every year, but drift does not matter here: a name that leaves the
Nasdaq-100 keeps being captured, which is more history, not a bug. A name that
joins gets added with one `python main.py TICKER`. Nothing re-reads this file to
decide what is "in".

It is also not a universe to scan. Nothing ranks these against each other — see
the Interfaces section of options-quant.md. Capture breadth and cross-sectional
ranking are different things, and only the first one is happening.

Composition as of 2026-08-14: Nasdaq-100 plus the four broad-market ETFs. Any
ticker that no longer trades simply fails once and is logged; it costs one line
in the capture log and nothing else.
"""

NASDAQ_100 = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
    "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO", "AXON", "AZN", "BIIB", "BKNG",
    "BKR", "CCEP", "CDNS", "CDW", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD",
    "CSCO", "CSGP", "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA", "EXC",
    "FANG", "FAST", "FTNT", "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX",
    "INTC", "INTU", "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "LULU", "MAR",
    "MCHP", "MDLZ", "MELI", "META", "MNST", "MRVL", "MSFT", "MU", "NFLX", "NVDA",
    "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR",
    "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SNPS", "TEAM", "TMUS", "TSLA",
    "TTD", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY", "XEL", "ZS",
]

# Index ETFs. Their chains are several times deeper than a single name's — SPY
# alone runs to five figures of contracts — so they carry a disproportionate
# share of the storage cost. Kept because index vol is the reference every
# single-name VRP is implicitly quoted against.
ETFS = ["SPY", "QQQ", "IWM", "DIA"]

CAPTURE_SEED = sorted(set(NASDAQ_100 + ETFS))
