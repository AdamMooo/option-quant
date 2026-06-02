# mx-options Roadmap

## Phase 1 — Signal validation and quality filters

### Goal
Make the scanner a higher-confidence signal screen by auditing core metrics, separating quality from direction, and adding contract-level filters.

### Tasks
- Audit current scoring logic in `analysis/scorer.py` and `config.py`.
- Confirm IV units, HV units, momentum sign conventions, and `VRP` calculation.
- Refactor scoring to expose `quality_score` and `direction_score` separately.
- Add strict filters for spread, open interest, and ATM proximity.
- Update `main.py` output to show stock context and score breakdown.
- Capture research findings in `.planning/research/deep-research.md`.

### Done when
- `main.py` still runs as a scanner.
- Top-ranked contracts are filtered for quality before direction.
- Score breakdown is visible and explainable.

## Phase 2 — Live validation instrumentation

### Goal
Build the first real validation layer so the scanner can be measured against actual outcomes.

### Tasks
- Add `scripts/track_picks.py` to store daily top picks.
- Define a tracking schema: ticker, contract, score, quality, direction, underlying price, timestamp.
- Implement horizon outcome tracking at 5/10/20 days for underlying move and option move.
- Add a summary script to calculate hit rates and average returns.

### Done when
- The repo contains a pick-tracking script and sample log.
- The system can report whether top picks are improving over time.

## Phase 3 — Tuning, safety, and deployment readiness

### Goal
Use validation data to tune weights and add guardrails for reliable live use.

### Tasks
- Tune `SCORING_WEIGHTS` based on tracked performance.
- Add optional conservative mode / more restrictive filters.
- Add `--strategy` or `--mode` for `scan`, `validate`, `track`.
- Document recommended usage and limitations.

### Done when
- We have a validated default configuration.
- There is a clear path for live usage and ongoing monitoring.
