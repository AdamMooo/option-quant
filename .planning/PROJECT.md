# mx-options

TSX 60 options scanner — CBOE US-listed ADRs (USD).

## Purpose

Surface the most attractive option contracts for a small-to-medium account by combining option market structure, liquidity, and the underlying symbolehavior.

## Current status

- Existing CLI-first scanner is implemented in `main.py`.
- It already fetches CBOE delayed option chains, computes Greeks, and scores contracts.
- The current system is more of a signal-ranking screen than a validated trade strategy.

## Architecture

- `main.py` — CLI entry point and symbol pipeline
- `config.py` — universe, ticker mapping, scoring weights, constants
- `analysis/greeks.py` — BS IV inversion and Greeks fallback
- `analysis/metrics.py` — IVR, IVP, VRP, ATM IV, enrichment
- `analysis/scorer.py` — composite contract score
- `analysis/volatility.py` — realized volatility and momentum from underlying prices
- `data/fetcher.py` — CBOE JSON + yfinance price history + caching
- `data/cache.py` — SQLite-based TTL cache and IV history storage
- `output/display.py` — terminal presentation

## Success criteria

- The scanner produces candidate contracts whose underlying direction and option profile align.
- The scoring is transparent and decomposed into quality versus directional signal.
- There is a reproducible validation path to measure post-selection performance.
- The project remains CLI-first and lightweight, suitable for continued iteration without a UI.

## Constraints

- Python 3.11+ only.
- Do not introduce new data sources beyond CBOE delayed quotes and yfinance price history.
- Preserve the existing TSX ADR mapping and US liquid universe unless a new symbol is explicitly justified.
- No option execution engine. This is a signal screen and validation tool.
- No network calls in tests.
