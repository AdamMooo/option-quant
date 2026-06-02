---
milestone: v1.0
status: planning
stopped_at: "phase planning"
last_activity: "2026-05-25"
percent: 0
completed_phases: 0
total_phases: 3
current_phase: 1
---

# mx-options — State

**Current focus:** Phase 1 planning — validate scanner signals and add quality filters

## Accumulated decisions

- Data source: CBOE delayed quotes API (free, ~15 min delay) + yfinance price history
- Scanner is a signal-ranking screen, not a fully validated trading strategy
- IVR/IVP accuracy improves over time as `.cache/` IV history accumulates

## Next actions

- Complete Phase 1: verify metrics, separate quality/direction, add contract filters
- Build Phase 2 validation instrumentation for tracking real top picks
- Keep the project CLI-first and avoid adding a UI until validation succeeds
