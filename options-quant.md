---
type: project
---

# Options-Quant

Last updated: 2026-08-14

Single-stock option market description. You bring the thesis; this repo tells you what the option
market on that name currently costs, and what it is pricing that you might disagree with.

Pulled in from `github.com/AdamMooo/option-quant` on 2026-08-14 and re-scoped on arrival. The
mandate below replaces everything in `.planning/` — that directory is now history, not direction.

## Mandate

**One underlying at a time. Describe, do not rank.**

The tool takes a single stock ticker and reports the state of its option market completely enough
that a human holding a view can price the expression of that view. It does not form the view.

This is a deliberate inversion of what the repo was. The inherited code spent 45% of its scoring
weight on inferring *direction* from moving averages, RSI, momentum and relative strength — a
question that was never asked, answered badly (see Post-mortem), and answered in a form that could
not be checked.

## Two layers, and only one of them is buildable today

**Layer 1 — Description.** Deterministic, verifiable, no opinion. This is the whole near-term
project.

| Component | What it answers |
|---|---|
| ATM IV term structure | Is the front month bid relative to the back? Where is the earnings kink? |
| Skew by delta, per expiry | What is the market paying for downside vs upside? Is the put skew steep by this name's own standards? |
| IV vs realized, signed | Are options rich or cheap here — and by how much, in vol points, against which realized window? |
| Liquidity map | Which strikes and expiries can actually be traded — spread in cents and as % of mid, OI, volume |
| Event calendar | Earnings date and recent news (Finnhub), as *context on the calendar*, not as a score deduction |
| Greeks at a decision point | Delta/gamma/theta/vega for the contracts you are actually looking at, scale-normalized |

**Layer 2 — Opportunity.** Open research question. Explicitly *not* a feature to be hand-tuned into
existence — the previous attempt is the cautionary tale. It gets the same treatment the sibling
repos give their claims: preregister, measure, accept the answer.

Layer 2 is gated on Layer 1, twice over: it needs the descriptive primitives, and it needs the
point-in-time archive that Layer 1 produces as a byproduct.

## Why the recording matters more than the analytics

IV rank and IV percentile in the inherited code were computed from a local SQLite cache that starts
empty and gains one observation per day *per day you happen to run the scanner*. On a fresh clone
they return `None`, and the score silently substituted 50. Nothing in the repo has ever had a real
52-week IV history.

Every question worth asking here — is this vol cheap, is this skew unusual, does this term structure
mean anything — is a question about *where today sits in this name's own distribution*. That
requires history nobody in this stack currently has.

So the first real deliverable is an **append-only point-in-time chain archive**: every fetched chain
snapshot written once, never rewritten, timestamped at fetch. It is boring and it is the thing that
unblocks everything else. [[equity-cover-call-strategy-single-stock]] independently reached the same
conclusion from the other direction — it recorded pre-2021 IV history as "the one purchase now
justified."

## Point-in-time discipline

Adopted from the sibling repos, because the inherited code violated it structurally.

| Leak | State |
|---|---|
| IV history keyed by *run date* with `INSERT OR REPLACE` — second run of the day overwrote the first | **CLOSED** 2026-08-14. Table deleted; archive is append-only with a regression test. |
| No as-of stamp distinguishable from run date | **CLOSED** 2026-08-14. `source_ts` (exchange) and `captured_at` (fetch) stored separately. |
| `yfinance auto_adjust=True` returns retroactively dividend-adjusted closes; realized vol from them is not what was observable | **LATENT.** Fixed *going forward* — unadjusted OHLCV is now captured per snapshot. But `analysis/volatility.py` still reads yfinance for history predating the archive, and will until the archive is deep enough to replace it. Anything computed from that path today is not point-in-time valid. |
| Realized vol compared against implied over a *different* window | **OPEN.** See the AAPL finding below. |

A fuller leak register in `docs/POINT-IN-TIME-DISCIPLINE.md`, in the format used by
[[equity-cover-call-strategy-single-stock]], follows once there are enough entries to warrant it.

## What survives from the inherited code

| Keep | Why |
|---|---|
| `data/fetcher.py` | Working CBOE delayed-quote feed with a correct OCC symbol parser. Genuinely useful and free. |
| `analysis/greeks.py` | Correct Black-Scholes, Brent IV inversion, sane per-day theta and per-1%-vol vega. |
| `data/cache.py` | TTL cache. Becomes the archive's foundation once it stops overwriting. |
| `data/demo.py` | Offline synthetic mode. Keeps tests network-free. |
| `data/macro.py` | VIX / VIX3M / term structure. Useful context header. |
| `analysis/volatility.py` → `compute_hv` | Realized vol. The rest of the module is direction inference and goes. |

## What is deleted

- `analysis/scorer.py` entirely, plus `SCORING_WEIGHTS`, `--min-score`, and the `Score`/`Q`/`D`
  columns. Confirmed 2026-08-14.
- `TSX_TO_CBOE`, `CBOE_TO_TSX`, `--universe tsx`, and `.TO` symbol resolution. Confirmed
  2026-08-14. The repo has not been TSX-focused since the Nasdaq-100 switch.
- `cmd_scan`, `UNIVERSE`, `US_UNIVERSE`, `--top` — universe-wide ranking is not the mandate.
- `compute_technicals` (MA20/50/200, RSI14, RS vs SPY) and momentum confluence — direction
  inference, which the user supplies.
- Earnings-as-penalty. The earnings *date* is retained and promoted to the event calendar.

## Post-mortem: why the composite score is being deleted rather than fixed

Recorded so the same thing is not rebuilt. Verified numerically 2026-08-14.

1. **Sign-blind on the metrics that carry the trade.** `_ivr_score` was `|IVR − 50| × 2` and
   `_vrp_score` was `|VRP| × 5`. IVR 95 and IVR 5 scored identically at 90 — opposite trades, same
   score. 45% of quality weight rewarded deviation magnitude while discarding the sign.
2. **Momentum saturated into a sign function.** `momentum()` returns a decimal;
   `enrich_contract` multiplied by 100 and overwrote the field; `_momentum_confluence_score`
   multiplied by 500 again. Anything above ~0.084% clamped to 100. The docstring claimed
   "magnitude matters."
3. **Gamma score was a bet on cheap stocks.** Γ = φ(d₁)/(Sσ√T) scales as 1/S, and the raw value was
   multiplied by 1000 and clamped. ATM 30-DTE at IV 30%: $20 stock → 100, $500 stock → 9.2. At 15%
   weight this systematically ranked low-priced underlyings. Scale-free alternative is dollar-gamma,
   Γ·S²/100.
4. **Quality capped at 90, not 100.** The six weights used summed to 0.90;
   `SCORING_WEIGHTS["momentum"] = 0.10` was orphaned when momentum moved to `direction_score` with
   its own hardcoded 0.20. `config.py` still asserted "must sum to 1.0." The `--min-score 65`
   default was a threshold against a misunderstood scale.
5. **Opposing theses averaged together.** `direction_score` blended trend continuation (MA
   alignment, momentum, RS — 65%) with mean reversion (`_rsi_score` rewarded oversold for calls —
   20%). Names rarely score high on both, so the average collapsed toward 50 for nearly everything.
   Averaging factors with opposing signs is a known failure mode; the fix is gating, not weighting.
6. **Never measured, and unmeasurable retroactively.** Phase 2 (validation) was never built, output
   was never written to disk, so there is no record of what the scanner said on any past day. Every
   weight and breakpoint was a guess that could not be scored.

The through-line: it attempted Layer 2 without Layer 1 and without the research.

## Layer 2 research — the literature to read before proposing anything

Naming the standard terms so the eventual claim is preregistered against known results rather than
invented fresh.

- **Variance risk premium.** Carr & Wu (2009); Bollerslev, Tauchen & Zhou (2009). IV exceeds
  subsequent realized vol on average — compensation for bearing vol risk. **Direct implication: on
  average, buying options loses.** This is the most important prior for this repo, and it points
  against the previous milestone's long-option thesis.
- **Cross-section of option returns.** Goyal & Saretto (2009) — the IV-minus-historical-vol spread
  predicts delta-hedged option returns. This is the closest published result to what the old scorer
  was groping toward, and its sign says *sell* when IV−HV is high, not buy.
- **Delta-hedged option gains.** Bakshi & Kapadia (2003) — the correct outcome variable. Any test
  of "was this option cheap" must strip out direction, or it is a stock-picking signal wearing an
  options costume.
- **Skew as a predictor.** Xing, Zhang & Zhao (2010) — steep put skew predicts negative underlying
  returns.
- **Earnings and the term-structure kink.** Dubinsky & Johannes — event vol and post-announcement
  IV crush.
- **IV rank / IV percentile** are retail-practitioner constructs, not literature terms. Useful as
  description; no published evidence base as a signal.

## Status

Definition agreed and deletion pass done 2026-08-14 (`731a570`, on `main`, not pushed). 879 lines
removed, 619 added. Tests pass offline (6); live CBOE path verified against AAPL.

`main.py TICKER` now prints: macro header, spot, realized vol at 10/20/30/60d, ATM IV and its gap
to 30d realized, a jump caution when one day dominates the realized window, IV history depth,
earnings proximity, recent news, and the filtered chain with Greeks and liquidity.

**Archive built 2026-08-14.** `data/archive.py` + `archive.py` CLI. Append-only enforced by SQLite
triggers, not by convention — `UPDATE` and `DELETE` raise on all three tables. Verified live: four
symbols captured, re-capture appends rather than clobbers, `main.py` snapshots every symbol you
look at.

CBOE turned out to supply three things the old code ignored:

| Field | Why it matters |
|---|---|
| `timestamp` | The exchange's own quote time. Stored as `source_ts`, separate from our `captured_at`. Conflating those two is how lookahead gets in. |
| `iv30` | CBOE's **constant-maturity** 30-day IV. Now the basis for IVR/IVP instead of a nearest-ATM front-month contract, which rolls between expiries and so moves when the calendar moves rather than when vol does. |
| Underlying OHLCV | **Unadjusted**, captured at snapshot time. This is the permanent fix for the `yfinance auto_adjust` leak — going forward there is a price series that cannot be retroactively rewritten. |

The old `iv_history` table is gone. It used `INSERT OR REPLACE` keyed on run date, so a second run
in a day silently overwrote the first. There is now a regression test for exactly that.

Storage: ~149 bytes per contract row, ~3,300 contracts per symbol per snapshot. Daily capture of 20
symbols is roughly **2.5 GB/year**. Acceptable for now; if it needs trimming the knob is skipping
zero-OI contracts at capture, which is a decision that cannot be undone, so it is not the default.

**Next: neither analytics nor Layer 2 — coverage.** The archive is worth exactly as much as the
number of days in it, and a day not captured is unrecoverable. Everything else is downstream of
getting a scheduled daily capture running.

### Found during the deletion pass

AAPL on 2026-08-14 printed ATM IV 20.6% against 30d realized 34.9% — a −14.3 vol point gap that
reads as "options cheap" and is almost certainly not. One −7.6% day (2026-07-31, the earnings
reaction) contributes 8.4 of those 34.9 vol points; ex-that-day realized is 26.4%. And the 20.6%
implied prices a forward window containing *no* earnings, because AAPL has already reported.

Two distinct problems, both now flagged in the output rather than fixed:

1. **Close-to-close realized vol is not robust to jumps.** The estimator has a fat-tailed sampling
   distribution and a single gap moves the annualized number by 8+ points. The literature fix is a
   jump-robust estimator — **bipower variation** (Barndorff-Nielsen & Shephard 2004), which
   separates the continuous diffusion component from jumps. Not built.
2. **VRP needs a matched window.** Comparing trailing realized to forward implied is only
   meaningful if both windows contain the same events.
   [[equity-cover-call-strategy-single-stock]] calls this matched-window RV and already
   implements it in `src/outcomes.py`.

Until both are addressed, the IV-minus-RV number on this screen is description, not evidence.

## Known issues carried in from upstream

- `.env.example` was removed upstream (`e7b3a51`); Finnhub is now load-bearing for earnings and
  news, so it needs restoring.
- Sequential fetch across symbols with no concurrency — irrelevant once the tool is single-symbol.
- `config.py` module docstring describes the TSX map as the repo's purpose.
- Repo name is singular (`option-quant`) while the folder is plural (`options-quant`).
- Not registered in the [[CLAUDE]] repo table at vault root.
- The parent `systematic-investing-research/` still documents `regime-detection`, which no longer
  exists on disk. The previous milestone's regime-overlay design depended on it.
