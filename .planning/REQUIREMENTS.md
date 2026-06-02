# mx-options Requirements

## Core functional requirements

1. Preserve the existing universe and symbol mapping.
   - TSX ADRs via `TSX_TO_CBOE`.
   - Selected US liquid symbols in `US_UNIVERSE`.

2. Maintain the existing data sources.
   - Options from CBOE delayed quotes API.
   - Underlying price history from yfinance.
   - Cache data in `.cache/mx_options.db` using the existing cache helper.

3. Compute stock-based context for every symbol.
   - `hv10`, `hv20`, `hv30`, `hv60` from underlying daily closes.
   - `mom20` and `mom60` returns on the underlying symbol.
   - Expose these values in the per-symbol detail view.

4. Compute option-quality metrics reliably.
   - `IVR` and `IVP` from 52-week ATM IV history.
   - `VRP = IV - HV30`.
   - `gamma`, `spread_pct`, `open_interest`, `dte`.
   - ATM IV selection from the nearest ATM call in the front-month range.

5. Separate quality and direction within scoring.
   - Introduce a `quality_score` component for IV and contract quality.
   - Introduce a `direction_score` component for underlying momentum.
   - Rank only contracts that pass minimum quality thresholds.

6. Add hard contract filters.
   - Enforce tight spread and minimum open interest.
   - Prefer ATM / near-ATM strikes in the target DTE range.
   - Optionally reject directional trades when stock momentum favors the opposite side.

7. Add validation instrumentation.
   - Record daily top picks with contract metadata.
   - Track outcomes at future horizons (e.g. 5, 10, 20 days).
   - Generate summary metrics such as hit rate and average return.

8. Make the score explainable.
   - Show the component contributions clearly in output or logs.
   - Keep the score range 0–100.
   - Allow sorting by `score`, `ivr`, `vrp`, `gamma`, `volume`.

## Non-functional requirements

1. CLI-first design.
   - The tool should be usable from `python main.py` and `python main.py --symbol SHOP`.
   - Additional scripts may be added under `scripts/` for validation.

2. Minimal new dependencies.
   - Use the existing `rich`, `yfinance`, `requests`, `numpy`, `pandas`, `scipy` stack.
   - Do not add heavy UI frameworks.

3. Testable code.
   - Add tests for scoring, momentum, and metric calculations.
   - Avoid network calls in unit tests.

4. Sustainable workflow.
   - Document the project and phase plan in `.planning/`.
   - Track state and next actions in `.planning/STATE.md`.
