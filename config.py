"""
Constants for the single-stock option market view.

No universe lives here. The tool takes one ticker at a time — see options-quant.md.
"""

# Cache TTLs in seconds
CACHE_TTL_OPTIONS = 30 * 60   # 30 minutes
CACHE_TTL_PRICES = 60 * 60    # 1 hour

# Risk-free rate (US, annualized) — update periodically
RISK_FREE_RATE = 0.053

# CBOE options API base URL
CBOE_API_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json"

# Display filters. These narrow what is shown; they are not a quality judgement.
MAX_SPREAD_PCT = 15.0
DEFAULT_MIN_OI = 10
