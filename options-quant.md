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
| `quote_date` took `source_ts[:10]` on a **UTC** stamp, so any capture after 20:00 ET was filed under the *next* trading session — inventing a session, and letting one session contribute two observations to the distribution IVR/IVP rank against | **CLOSED** 2026-08-14. `session_date()` converts to `America/New_York`, and both `iv30_series` and `summary` now derive the session date **on read**, so rows already written under the old rule are re-attributed without rewriting history. Two regression tests, one covering EST and EDT. |
| A capture taken **before the 09:30 ET open** carries the previous session's quotes but stamps the current date | **OPEN, narrow.** The 16:45 scheduled job is well clear of it; ad-hoc morning runs are not. Fixing it needs a session-open rule, not just a timezone. |

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

## Interfaces

Agreed 2026-08-14. This section is the boundary contract; it constrains what may be built, not
just what is built today.

### The boundary

```
Options Quant  →  descriptive market observations
                  (later)  →  Portfolio Manager  →  broader portfolio context
```

[[portfolio-manager]] is a **potential downstream consumer** of this repo's observations. It is not
a dependency in either direction and must not become one.

Prohibited from crossing into this repo, in any form:

- Imports of `portfolio-manager` (or any sibling repo's) modules.
- Allocation logic, position sizing, band or sleeve limits.
- Execution, order construction, or broker connectivity.
- Any decision rule that consumes portfolio state to decide what this repo reports.

This repo must remain independently runnable and independently testable with the sibling repos
absent from disk. That property is load-bearing, not incidental.

### Cross-sectional ranking is not in the mandate

`Detect → Quantify → Describe`, not `Detect → Quantify → Rank`.

Not to be reintroduced under any name: `cmd_scan`, `UNIVERSE`, `--top`, `analysis/scorer.py`,
composite anomaly scores, cross-sectional ranking, or an equivalent mechanism relabelled. Calling
a composite an "anomaly magnitude" does not fix it — the defect is combining heterogeneous
families into one scalar, and that defect is independent of the label. See the post-mortem above
for the six numbered reasons.

**The ranking question is open, not settled against.** It is a Layer 2 research question, gated on
preregistration and measurement in the style of [[equity-cover-call-strategy-single-stock]]. What
is prohibited is reintroducing it *silently*, as a byproduct of some other feature. Reopening it
means editing this section first.

Three things that are ordering but are **not** the prohibited rank, so they are not confused later:

| Mechanism | Status | Why it differs |
|---|---|---|
| `--sort iv\|vrp\|gamma\|oi\|spread` | Allowed, exists | Orders contracts *within one chain*. A visibility filter on one name's own strikes. |
| Within-name historical flagging | Allowed in principle, gated on depth | "This name's front IV sits high in *its own* trailing distribution." One name against itself. |
| Ordering names against each other | Prohibited | Requires a universe and a comparable scalar across names. This is the deleted object. |

### Surfacing, diligence prompts, and what "unusual" requires

This repo is meant to help a human understand a name's option market and notice what is worth
investigating. That is not in tension with the above, provided the distinction holds:

- A **pointer to attention** — "front-month IV is at the top of this name's own 6-month range,
  skew is steeper than its own median, earnings fall inside this expiry; go look" — is
  description with a stated threshold. Legitimate.
- A **recommendation** — "buy this", or a scalar that orders candidates — is not.

The rules that keep the first from decaying into the second: every flag carries its own units and
the provenance of its threshold; flags are never summed, averaged, or counted into a score; the
count of triggered flags is not itself a measure of anything.

Available **today**, with no archive history, because they are self-contained facts about the
current chain: term-structure shape and where the earnings kink sits, skew by delta, VRP sign and
magnitude in vol points, liquidity by strike, event calendar, Greeks at a chosen contract.

Requires history, therefore **gated**: the word *unusual*. Every form of "is this high" is a
question about where today sits in this name's own distribution, and that distribution does not
exist yet.

### Structured snapshot/export — future, gated

A structured export is conceptually compatible with the mandate: one ticker, one timestamp, the
Layer 1 observations that actually exist, as descriptive fields with explicit units and
provenance. No composite score, no cross-sectional rank, no implied recommendation.

It is **not** the next implementation priority, and it is not to be built ahead of the archive:

```
Reliable daily capture → historical archive → distribution → normalization → structured interface
```

Any field requiring historical normalization is gated on archive depth. `iv_percentile` and
`iv_rank` are therefore **future derived-on-read measurements, not currently valid fields**. They
must never be defaulted — the silent `None → 50` substitution is precisely the failure the archive
was built to prevent. The guard is live at `analysis/metrics.py:26` (`MIN_IV_OBSERVATIONS = 10`,
returning `None` below that), and `iv_history_depth` is surfaced in the output so the reader knows
whether to believe them.

Missing capture days are unrecoverable. Coverage outranks any downstream schema.

> **Capture first. Describe honestly. Normalize when history exists. Do not rank by accident.**

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

Storage, **measured 2026-08-14** after the universe expansion (103 tickers, 305,468 rows):
**143 bytes per contract row**. One full nightly round is 231,074 contracts ≈ **33 MB/night**, so
the seed universe costs **~8.3 GB/year** against 699 GB free. Chain depth is wildly uneven — SPY
14,588 and QQQ 12,738 contracts against AEP 478 — so the four index ETFs carry a disproportionate
share of the total.

**The zero-OI trim was considered and rejected.** Zero-OI contracts are only **18.9%** of stored
rows — trimming them saves about a fifth of the total while permanently destroying the record of
where open interest *first appears*, which is precisely the observation you would want for studying
new positioning. Small, irreversible, and pointed at the wrong thing. Not the default and not
recommended.

### Scheduled capture

**Running since 2026-08-14.** `scripts/capture_daily.ps1`, registered as the Windows task
`options-quant-daily-capture`, daily at 16:45 local — after the close, so the delayed feed carries
the closing chain. Verified through the Task Scheduler path itself, not just a manual run
(`LastTaskResult: 0`).

- **No watchlist file.** The script captures `--from-archive`, so the tracked set is whatever is
  already in the archive. `main.py TICKER` snapshots any name you look at, and the schedule picks it
  up the next day. A list that has to be kept in sync is a list that goes stale.
- **The universe is 103 names** (104 attempted; ANSS no longer trades) — Nasdaq-100 plus
  SPY/QQQ/IWM/DIA — enrolled 2026-08-14 from
  `data/seed.py` via `archive.py capture --seed`. That file is a **seed, not a membership list**: it
  is read once to enrol and never consulted again, so index rebalancing cannot silently rot it. A
  name that leaves the index keeps being captured, which is more history, not a bug.
  **Capture breadth is not a scan** — nothing ranks these against each other. See Interfaces.
- **Hardened for scale**, because at ~100 names per-night failures go from unlikely to certain:
  3 attempts with 2s/5s backoff (a transient failure is a permanently lost day — there is no
  backfill), 0.4s throttle between symbols (being rate-limited costs *every* name that night, not
  one), and a nonzero exit only when **>10%** of the run fails. That last split is deliberate: the
  exit code catches systemic breakage, while `archive.py status` catches the single ticker that
  quietly died. A job that reports failure because one name delisted is a job you learn to ignore.
- **`status` flags staleness against the archive, not the wall clock.** On a holiday every ticker is
  a day behind and nothing is wrong; a ticker that has stopped updating falls behind *its peers*.

**CBOE serves stale quotes for some names, and it caught it on the first night.** ODFL, PAYX, PCAR
and VRTX were fetched at 02:28 UTC on 2026-08-15 but came back stamped `source_ts` **2026-08-13** —
up to two days old — while the other 99 names were current. Nothing is wrong with the fetch; the
vendor is serving a stale cache for those symbols.

This is the entire reason `captured_at` and `source_ts` are stored as separate facts. Because the
session date derives from `source_ts`, those four are correctly filed under the session they
actually came from rather than the night we fetched them. The cost is real but honest: those names
will have **holes** in their coverage, visible as a lower `trading_days` in `status`, rather than
four silently wrong observations. A capture-time warning when `source_ts` lags `captured_at` by more
than a session would make it visible sooner; `status` already makes it visible eventually.
- **`-StartWhenAvailable` is set**, so a machine that was asleep at 16:45 still captures when it
  wakes. A missed day cannot be backfilled, so the default of silently skipping was not acceptable.
- **Weekends are skipped by rule; holidays are not.** Skipping holidays needs a hardcoded calendar,
  and a stale table fails silently — the failure mode [[portfolio-manager]] hit with `_SYMBOL_REMAP`
  the same day. A holiday run appends a snapshot carrying the prior session's `quote_date`, which
  `iv30_series` already dedupes. The cost is disk, not correctness.
- Log: `logs/capture-YYYY-MM.log` (gitignored).

```powershell
Get-ScheduledTaskInfo -TaskName 'options-quant-daily-capture'   # did it run, what did it return
Unregister-ScheduledTask -TaskName 'options-quant-daily-capture' -Confirm:$false   # remove
```

**Next: still coverage, then the two unbuilt Layer 1 rows.** The archive is worth exactly as much as
the number of days in it. `iv_rank`/`iv_percentile` stay `None` until 10 trading days (~2026-08-28);
a range that means what its name implies needs a year.

The two Layer 1 components in the table above that are **promised and not implemented** are ATM IV
term structure and skew by delta — `output/display.py` has only the macro header, symbol header,
news and chain table. Both are self-contained facts about a single day's chain, so neither is gated
on archive depth, and both say more about what the market is pricing than the flat contract table
does. They are the honest next build after capture is safely running.

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

- ~~`.env.example` was removed upstream (`e7b3a51`)~~ — restored and tracked, 2026-08-14.
- Sequential fetch across symbols with no concurrency — irrelevant once the tool is single-symbol.
  Capture across the 103-name universe throttles and retries instead (`archive.py`).
- `config.py` module docstring describes the TSX map as the repo's purpose.
- Repo name is singular (`option-quant`) while the folder is plural (`options-quant`). Recorded in
  the vault [[CLAUDE]] table rather than fixed — renaming the remote breaks the clone URL for no
  gain.
- ~~Not registered in the [[CLAUDE]] repo table at vault root.~~ — registered 2026-08-14, in both
  [[CLAUDE]] and [[INDEX]], as sharing the `systematic-investing-research/` container **without**
  being governed by the charter.
- The parent `systematic-investing-research/` still documents `regime-detection`, which no longer
  exists on disk. The previous milestone's regime-overlay design depended on it. **Still open, and
  wider than this repo:** the container now holds `core-risk-overlay` (active,
  `github.com/AdamMooo/core-risk-overlay`) where `regime-detection` used to be, and the vault docs
  have not caught up. The four governance docs were stored inside `regime-detection` for
  durability, so on disk they are gone.

## Memory

Personal quant project on the AdamMooo GitHub account, pulled in from `option-quant` on
2026-08-14 and re-scoped on arrival. It **describes one option market at a time and does not
rank**: no scanner, no top-N, no composite score — that design was deleted for cause the day the
repo landed, and the prohibition is written against the *mechanism* (combining unlike units), not
the label. Surfacing "opportunities" is Layer 2, a research question gated on archive depth, not a
feature to hand-tune. Shares the `systematic-investing-research/` container with the governed
stack but is not part of it.

## Related

- [[INDEX|Vault home]]
- [[systematic-investing-research/portfolio-manager/portfolio-manager]] — potential downstream
  consumer. Boundary in the Interfaces section above: descriptive observations only, PM owns any
  interpretation, and this repo must never import PM. **No feed is wired and none is being built.**
- [[equity-cover-call-strategy-single-stock]] — matched-window realized vol, already implemented
  there in `src/outcomes.py`
