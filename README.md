# options-quant

Single-stock option market description. One ticker in, the state of its option market out.

You bring the thesis. This tool does not form a view, rank contracts, or produce a score — it
describes what the option market currently costs, well enough that you can price the expression of
a view you already hold.

Mandate, design rules and the post-mortem of what this repo used to be: `options-quant.md`.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt
cp .env.example .env            # then fill in the keys
```

Python 3.11+.

| Key | Needed for | Without it |
|---|---|---|
| `FINNHUB_API_KEY` | Earnings date, company news | Both silently absent |
| `FRED_API_KEY` | Macro header | Falls back to the no-key FRED CSV endpoint (slower) |

## Use

```bash
python main.py NVDA
python main.py NVDA --moneyness atm --dte-min 21 --dte-max 45
python main.py NVDA --type call --sort vrp --limit 20
python main.py NVDA --demo                  # synthetic data, no network
```

Reports: macro header, spot, realized vol at 10/20/30/60d, ATM IV and its gap to realized, IV rank
and percentile, earnings proximity, recent news, and the filtered chain with Greeks and liquidity.

Contracts whose expiry spans the earnings date are marked `*` — they price an event the trailing
realized-vol window does not contain.

## The archive

`archive/chains.db` is an append-only, point-in-time record of every chain snapshot ever fetched.
It is the repo's long-lived asset: IV rank, IV percentile, and any future research all depend on
history that has to be accumulated day by day and cannot be reconstructed after the fact.

```bash
python archive.py capture AAPL MSFT NVDA    # append snapshots
python archive.py capture --from-archive    # re-capture everything already tracked
python archive.py status                    # coverage, readiness, disk size
```

`main.py` also snapshots every symbol you look at, but that is opportunistic. **Capture on a
schedule** — a day not captured is gone for good.

Rules, enforced by SQLite triggers rather than convention:

- INSERT only. No UPDATE, no DELETE, no INSERT OR REPLACE.
- Observations are stored; derived values are recomputed on read.
- `captured_at` (our fetch time) and `source_ts` (the exchange's stamp) are kept separate.
- Synthetic `--demo` data never enters the archive.

`.cache/` is a disposable TTL cache and can be deleted at any time. `archive/` cannot.

Storage runs about 149 bytes per contract row and ~3,300 contracts per symbol per snapshot — daily
capture of 20 symbols is roughly 2.5 GB/year.

## Reading the output honestly

Two caveats the tool prints for itself, worth understanding before you trust a number:

**IV rank and percentile need history.** Below 10 archived observations they report nothing rather
than guess, and a genuine 52-week range needs a year of daily capture. `archive.py status` shows
where each symbol stands.

**IV minus realized vol is not a mispricing.** Realized vol looks backward and is badly non-robust
to jumps — one earnings gap can move an annualized 30-day number by 8+ vol points. Implied looks
forward. If the two windows do not contain the same events, the gap between them is an artifact.
The tool flags both conditions; it does not correct for them.

## Tests

```bash
pytest tests -q
```

Offline by design — no test makes a network call.
