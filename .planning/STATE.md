---
milestone: v1.0
status: active
stopped_at: "phase 1 in progress"
last_activity: "2026-06-05"
percent: 40
completed_phases: 0
total_phases: 3
current_phase: 1
---

# mx-options — State

**Current focus:** Phase 1 — signal quality and filtering (in progress)

## Accumulated decisions

- Data source: CBOE delayed quotes API (free, ~15 min delay) + yfinance price history
- Scanner is a signal-ranking screen, not a fully validated trading strategy
- IVR/IVP accuracy improves over time as `.cache/` IV history accumulates
- IV stored as percentage (e.g. 61.0 = 61%) throughout the pipeline — CBOE returns decimal, multiplied by 100 on ingestion
- Direction score is multi-factor (MA alignment, RSI, momentum confluence, RS vs SPY, earnings proximity via Finnhub)
- Min composite score threshold: 65 (default) — scanner shows real setups only, no padding to top-N
- Deep ITM filter: |delta| > 0.95 and IV > 150% excluded

## What's working (2026-06-05)

- Full CBOE live scan across Nasdaq-100 universe
- IV correctly scaled — Greeks, VRP, IVR all in consistent units
- 5-factor direction score live — calls/puts score differently per stock
- Finnhub earnings proximity wired — penalizes direction score hard <7d to earnings
- SPY relative strength computed from yfinance
- `--min-score 65` default — today returned 9 real opportunities from ~50 symbols

## Next actions

- Phase 1 remaining: run daily for 2+ weeks to accumulate IVR/IVP history
- Phase 2: validation instrumentation — log top picks, track P&L vs random baseline
- Phase 3: UI or export (CSV/email digest) once signals are validated
