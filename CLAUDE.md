# mx-options

TSX 60 options scanner — CBOE US-listed ADRs (USD).

## What it does

Scans the TSX 60 universe mapped to liquid CBOE-listed tickers, pulls delayed option chains, computes Greeks + volatility metrics, and ranks contracts by a composite score.

## Run

```bash
# Full scan (live CBOE data, ~50 symbols)
python main.py

# Single symbol deep-dive
python main.py --symbol SHOP

# Demo mode (no network)
python main.py --demo

# Common filters
python main.py --type call --moneyness otm --dte-min 21 --dte-max 45 --sort ivr
```

## Project layout

```
config.py          TSX→CBOE ticker map, scoring weights, constants
main.py            CLI entry point
analysis/
  greeks.py        Black-Scholes Greeks (delta, gamma, theta, vega, IV)
  metrics.py       IVR, IVP, VRP, ATM IV, enrichment
  scorer.py        Composite scoring
  volatility.py    HV computation, momentum
data/
  fetcher.py       CBOE API fetch + yfinance price history + caching
  cache.py         Disk cache (TTL-based)
  demo.py          Synthetic data for offline testing
output/
  display.py       Rich terminal tables
```

## Key constants (config.py)

- `SCORING_WEIGHTS` — adjust per-metric weights (must sum to 1.0)
- `RISK_FREE_RATE` — update periodically (currently 5.3%)
- `CACHE_TTL_OPTIONS` / `CACHE_TTL_PRICES` — 30 min / 1 hr
- `MAX_SPREAD_PCT` — contracts with spread > 15% are excluded
- `DTE_SWEET_MIN/MAX` — 21–45 days is the scoring sweet spot

## Data sources

- Options chains: CBOE delayed quotes API (free, ~15 min delay)
- Price history: yfinance

## Environment

```bash
python3 -m venv .venv
pip install -r requirements.txt
```

Python 3.11+.
