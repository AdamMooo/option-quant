# mx-options Deep Research

## Current system analysis

- `main.py` fetches CBOE option chains and yfinance price history.
- The underlying symbol price history feeds `analysis/volatility.py` for realized volatility and momentum.
- `analysis/metrics.py` computes IV-based metrics and enriches every contract with HV, VRP, IVR, and IVP.
- `analysis/scorer.py` currently compresses option quality and momentum into a single `score`.
- The output is a ranked terminal table, not a performance-tracked strategy.

## What the scanner already captures

- Option-level signals:
  - `IV%` from CBOE or BS fallback.
  - `IVR` and `IVP` from 52-week ATM IV history.
  - `VRP = IV - HV30`.
  - `gamma`, `delta`, `theta`, `vega`, `rho`.
  - `spread_pct` and `open_interest`.
  - DTE and moneyness filters.

- Underlying-symbol signals:
  - 20-day and 60-day momentum.
  - realized volatility over 10/20/30/60-day windows.

## Opportunities and risks

### Opportunity
- The existing model is a strong platform for a signal screen because it already blends both option market structure and underlying movement.

### Risk
- Momentum is only 10% of the score, so directional alignment is weak.
- The score is opaque: contracts can rank highly on cheap IV even if the underlying trend is against the option type.
- There is no outcome tracking, so the model has not been validated against real results.

## Recommended improvements

1. Separate quality from directional signal.
   - `quality_score` for IV + gamma + liquidity + DTE.
   - `direction_score` for underlying momentum.

2. Add a momentum threshold.
   - Reject calls when `mom20` is meaningfully negative.
   - Reject puts when `mom20` is meaningfully positive.

3. Add a dedicated tracking layer.
   - Log daily top picks.
   - Measure actual realized outcomes.
   - Enable weight tuning from data.

4. Keep the project CLI-first.
   - Use `scripts/` for validation instruments.
   - Keep the scanner output simple and explainable.

## Deep research conclusion

The current code is not yet a validated trading model. It is a good scanner, but it should not be treated as a full buy rule. The highest-leverage improvement is validation: track top picks, measure futures returns, and tune the scoring with real outcomes.
