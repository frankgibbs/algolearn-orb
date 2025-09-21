"""
Static stock configuration for ORB strategy
Contains the list of stocks to trade and stock-specific parameters
"""

# Static list of stocks to trade
STOCK_SYMBOLS = [
    "AAPL",  # Apple Inc.
    "MSFT",  # Microsoft Corporation
    "GOOGL", # Alphabet Inc. Class A
    "AMZN",  # Amazon.com Inc.
    "NVDA",  # NVIDIA Corporation
    "TSLA",  # Tesla Inc.
    "META",  # Meta Platforms Inc.
    "AMD",   # Advanced Micro Devices Inc.
    "SPY",   # SPDR S&P 500 ETF Trust
    "QQQ",   # Invesco QQQ Trust
]

# Stock-specific configurations (optional overrides)
STOCK_CONFIGS = {
    "TSLA": {
        "min_range_pct": 1.0,  # More volatile, needs bigger range
        "max_range_pct": 5.0
    },
    "NVDA": {
        "min_range_pct": 0.8,  # High volatility stock
        "max_range_pct": 4.0
    },
    "AMD": {
        "min_range_pct": 0.8,  # High volatility stock
        "max_range_pct": 4.0
    },
    "SPY": {
        "min_range_pct": 0.3,  # Less volatile ETF
        "max_range_pct": 2.0
    },
    "QQQ": {
        "min_range_pct": 0.4,  # Slightly more volatile than SPY
        "max_range_pct": 2.5
    }
}

# Default configuration for stocks not in STOCK_CONFIGS
DEFAULT_STOCK_CONFIG = {
    "min_range_pct": 0.5,  # Default minimum range as % of price
    "max_range_pct": 3.0   # Default maximum range as % of price
}

def get_stock_config(symbol):
    """
    Get configuration for a specific stock symbol

    Args:
        symbol: Stock symbol (e.g., "AAPL")

    Returns:
        Dict with min_range_pct and max_range_pct
    """
    return STOCK_CONFIGS.get(symbol, DEFAULT_STOCK_CONFIG)

def is_valid_symbol(symbol):
    """
    Check if a symbol is in our trading list

    Args:
        symbol: Stock symbol to check

    Returns:
        Boolean indicating if symbol is valid for trading
    """
    return symbol in STOCK_SYMBOLS