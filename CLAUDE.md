# options-quant

Single-stock option market description. Mandate, post-mortem and research frame in
`options-quant.md` — **read it before proposing any change.**

## What this repo is

Takes one stock ticker, reports the state of its option market: ATM IV term structure, skew by
delta, IV vs realized (signed), liquidity, Greeks, and the event calendar (earnings + news).

## What this repo is not

- **Not a scanner.** No universe scan, no ranked pick list, no top-N.
- **Not a direction model.** The user supplies the thesis. Do not add moving averages, RSI,
  relative strength, momentum, or anything else that infers which way the stock goes.
- **Not a composite score.** A single 0–100 number that blends unlike quantities was the previous
  design and was deleted for cause. Report the components with units.
- **Not an execution engine.**

Any proposal to surface "opportunities" is Layer 2 and is a *research* question — preregister and
measure it in the style of `equity-cover-call-strategy-single-stock`. Do not hand-set weights.

## Constraints

- Python 3.11+.
- Data sources: CBOE delayed quotes, yfinance price history, Finnhub (earnings + news). Do not add
  others without justification.
- No network calls in tests.
- Point-in-time discipline is binding. The archive is append-only — snapshots are written once and
  never rewritten. `yfinance auto_adjust=True` returns retroactively adjusted closes; do not use
  them for anything claiming to be observable-at-the-time.
- Minimal dependencies. Existing stack is `rich`, `yfinance`, `requests`, `numpy`, `pandas`,
  `scipy`, `python-dotenv`, `pytest`.

## State of the code

The clone is at upstream `26a655a` and **still contains the deleted-by-decision code** — the
scanner, the composite score, the TSX map and the direction factors. See `options-quant.md` for the
itemized removal list. `.planning/` is history, not direction.

## Run

```bash
python main.py SHOP                        # the view (also appends a snapshot)
python main.py SHOP --moneyness atm --dte-min 21 --dte-max 45
python main.py SHOP --demo                 # synthetic data, no network

python archive.py capture AAPL MSFT NVDA   # append snapshots on demand
python archive.py capture --from-archive   # re-capture everything already tracked
python archive.py capture --seed           # enrol the seed universe (data/seed.py), one-off
python archive.py status                   # coverage, readiness, staleness, disk size
```

Capture on a schedule — the archive only becomes useful with daily coverage, and a day not
captured is gone for good. **This is running:** `scripts/capture_daily.ps1` via the Windows task
`options-quant-daily-capture`, daily 16:45, logging to `logs/`. Details in `options-quant.md`
under "Scheduled capture".

## The archive is append-only

`data/archive.py` (`archive/chains.db`) is the long-lived asset; `data/cache.py` (`.cache/`) is
disposable. Never mix them.

- INSERT only. No UPDATE, no DELETE, no INSERT OR REPLACE. SQLite triggers enforce it.
- Store observations; derive everything else on read. DTE, VRP, moneyness and rank are not columns.
- Never write synthetic (`--demo`) data to the archive.
- `captured_at` (our fetch time) and `source_ts` (the exchange's stamp) are different facts. Do not
  collapse them.

## Environment

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`FINNHUB_API_KEY` in `.env` is required for earnings and news. Without it those fields are silently
`None`.
