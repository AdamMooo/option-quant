"""
TSX 60 → CBOE US-listed ticker mapping.
Only includes names with liquid CBOE-listed options.
Key: TSX ticker (with .TO), Value: CBOE/NYSE/NASDAQ ticker.
"""

TSX_TO_CBOE: dict[str, str] = {
    # Banks
    "RY.TO": "RY",    # Royal Bank
    "TD.TO": "TD",    # TD Bank
    "BNS.TO": "BNS",  # Bank of Nova Scotia
    "BMO.TO": "BMO",  # Bank of Montreal
    "CM.TO": "CM",    # CIBC
    "NA.TO": "NA",    # National Bank (limited CBOE liquidity)
    # Insurers
    "MFC.TO": "MFC",  # Manulife
    "SLF.TO": "SLF",  # Sun Life
    # IFC.TO removed — CBOE returns 403 (no US-listed options)
    # Energy
    "ENB.TO": "ENB",  # Enbridge
    "TRP.TO": "TRP",  # TC Energy
    "SU.TO": "SU",    # Suncor
    "CNQ.TO": "CNQ",  # Canadian Natural Resources
    "CVE.TO": "CVE",  # Cenovus
    "IMO.TO": "IMO",  # Imperial Oil
    "ARX.TO": "ARX",  # ARC Resources
    # Rail / Industrials
    "CNR.TO": "CNI",  # CN Rail (different CBOE ticker!)
    "CP.TO": "CP",    # CP Rail
    # WSP.TO removed — CBOE returns 403 (no US-listed options)
    "TRI.TO": "TRI",  # Thomson Reuters
    "BAM.TO": "BAM",  # Brookfield Asset Mgmt
    "BN.TO": "BN",    # Brookfield Corp
    "WCN.TO": "WCN",  # Waste Connections
    # Telecom
    "BCE.TO": "BCE",  # Bell Canada
    "T.TO": "TU",     # Telus (different CBOE ticker!)
    # Mining / Materials
    "ABX.TO": "GOLD", # Barrick Gold (different CBOE ticker!)
    "FNV.TO": "FNV",  # Franco-Nevada
    "WPM.TO": "WPM",  # Wheaton Precious Metals
    "CCO.TO": "CCJ",  # Cameco (different CBOE ticker!)
    "AGI.TO": "AGI",  # Alamos Gold
    "FM.TO": "FM",    # First Quantum (limited CBOE)
    "TECK.TO": "TECK",# Teck Resources (B shares on NYSE)
    # Tech
    "CSU.TO": "CSU",  # Constellation Software (limited CBOE)
    "SHOP.TO": "SHOP",# Shopify
    "CGI.TO": "GIB",  # CGI Group (different CBOE ticker!)
    "OTEX.TO": "OTEX",# OpenText
    # Utilities
    "FTS.TO": "FTS",  # Fortis
    "AQN.TO": "AQN",  # Algonquin Power
    "H.TO": "H",      # Hydro One
    # Real Estate / Infrastructure
    "BIP.TO": "BIP",  # Brookfield Infrastructure
    "BEP.TO": "BEP",  # Brookfield Renewable
    # Consumer / Retail
    "MG.TO": "MGA",   # Magna International (different CBOE ticker!)
    "QSR.TO": "QSR",  # Restaurant Brands
}

# Reverse map: CBOE ticker → TSX ticker (for display purposes)
CBOE_TO_TSX: dict[str, str] = {v: k for k, v in TSX_TO_CBOE.items()}

# US universe — liquid options, accessible premiums for small accounts
US_UNIVERSE: list[str] = sorted([
    # Broad market ETFs — tightest spreads, most liquid
    "SPY",   # S&P 500
    "QQQ",   # Nasdaq 100
    "IWM",   # Russell 2000 — lower price, great for small accounts
    "DIA",   # Dow Jones
    # Sector ETFs — directional macro plays, cheap premiums
    "XLE",   # Energy
    "XLF",   # Financials
    "XLK",   # Technology
    "XBI",   # Biotech — high IV, good for buying
    # Commodities ETFs
    "GLD",   # Gold
    "SLV",   # Silver — very affordable
    "GDX",   # Gold miners
    "USO",   # Oil
    # Rates / macro
    "TLT",   # 20yr Treasuries
    "HYG",   # High yield bonds
    # Large caps — accessible strikes, very liquid options
    "AAPL",
    "AMD",   # Lower price than NVDA, high IV
    "AMZN",
    "BAC",   # Bank of America — cheap per contract
    "F",     # Ford — very low premium, good starter
    "META",
    "NVDA",
    "PLTR",  # Lower price, high IV
    "SOFI",  # Low price, active options
    "MSTR",  # High IV, bitcoin proxy
])

# Combined universe (TSX ADRs + US)
UNIVERSE: list[str] = sorted(set(TSX_TO_CBOE.values()) | set(US_UNIVERSE))

# Scoring weights (must sum to 1.0)
SCORING_WEIGHTS = {
    "ivr": 0.25,       # IV Rank: low = cheap options
    "vrp": 0.20,       # VRP: negative = options underpriced vs realized vol
    "gamma": 0.15,     # Higher gamma = more reactive near ATM
    "liquidity": 0.20, # Tight spread + high OI
    "dte": 0.10,       # Sweet spot 21–45 days
    "momentum": 0.10,  # Stock price trend
}

# Cache TTLs in seconds
CACHE_TTL_OPTIONS = 30 * 60   # 30 minutes
CACHE_TTL_PRICES = 60 * 60   # 1 hour

# Risk-free rate (US, annualized) — update periodically
RISK_FREE_RATE = 0.053

# CBOE options API base URL
CBOE_API_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json"

# Bid-ask spread % above which contracts are excluded
MAX_SPREAD_PCT = 15.0

# Minimum open interest filter
DEFAULT_MIN_OI = 10

# DTE range for "sweet spot" scoring
DTE_SWEET_MIN = 21
DTE_SWEET_MAX = 45
