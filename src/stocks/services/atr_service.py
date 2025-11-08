"""
ATR Service - Calculate and cache Average True Range for academic ORB strategy

Based on "A Profitable Day Trading Strategy for The U.S. Equity Market"
(Zarattini, Barbon, Aziz 2024 - Swiss Finance Institute Paper No. 24-98)

ATR Formula:
    True Range (TR) = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = Simple Moving Average of TR over N periods
"""

from src import logger
from src.core.constants import CONFIG_ATR_PERIOD, CONFIG_ATR_STOP_MULTIPLIER
from datetime import datetime
from typing import Dict, Optional


class ATRService:
    """Service for calculating and caching Average True Range"""

    # In-memory cache: {(symbol, date, period): atr_value}
    _cache: Dict[tuple, float] = {}

    def __init__(self, application_context):
        """
        Initialize ATR service

        Args:
            application_context: Application context with client and state_manager

        Raises:
            ValueError: If application_context is None
        """
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.client = application_context.client
        self.state_manager = application_context.state_manager
        self.application_context = application_context

    def get_atr(self, symbol: str, use_yesterday: bool = True) -> float:
        """
        Get ATR for symbol (from cache or calculate on-demand)

        Uses yesterday's complete daily bars by default to avoid intraday calculation issues.

        Args:
            symbol: Stock symbol (required)
            use_yesterday: Use yesterday's close date for ATR calculation (default: True)

        Returns:
            ATR value in dollars

        Raises:
            ValueError: If symbol is None or configs are missing
            RuntimeError: If unable to calculate ATR
            TimeoutError: If IB data request times out
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        # Get and validate ATR period config
        atr_period = self.state_manager.get_config_value(CONFIG_ATR_PERIOD)
        if atr_period is None:
            raise ValueError("ATR_PERIOD is REQUIRED")

        # Convert to int if needed
        try:
            atr_period = int(atr_period)
        except (ValueError, TypeError):
            raise ValueError(f"ATR_PERIOD must be a valid integer, got: {atr_period}")

        if atr_period <= 0:
            raise ValueError(f"ATR_PERIOD must be positive, got: {atr_period}")

        # Get current date (Docker TZ already set to Pacific)
        cache_date = datetime.now().date()

        # Check cache
        cache_key = (symbol, cache_date, atr_period)
        if cache_key in self._cache:
            cached_atr = self._cache[cache_key]
            logger.debug(f"ATR cache hit for {symbol}: ${cached_atr:.2f}")
            return cached_atr

        # Cache miss - calculate ATR
        logger.info(f"Calculating {atr_period}-day ATR for {symbol}")

        # Fetch daily bars (need period + 1 to have previous close for first TR calculation)
        bars_needed = atr_period + 1
        duration = f"{bars_needed} D"

        contract = self.client.get_stock_contract(symbol)
        bars = self.client.get_historic_data(
            contract=contract,
            history_duration=duration,
            history_bar_size="1 day",
            timeout=10,
            whatToShow="TRADES"
        )

        if bars is None:
            raise TimeoutError(f"Timeout getting historical data for {symbol}")
        if bars.empty:
            raise RuntimeError(f"No historical data received for {symbol}")
        if len(bars) < atr_period:
            raise RuntimeError(
                f"Insufficient data for {atr_period}-day ATR on {symbol} "
                f"(need {atr_period}, have {len(bars)})"
            )

        # Calculate True Range for each bar
        true_ranges = []
        for i in range(1, len(bars)):
            current_bar = bars.iloc[i]
            prev_bar = bars.iloc[i - 1]

            high = current_bar['high']
            low = current_bar['low']
            prev_close = prev_bar['close']

            # TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        # Calculate ATR as simple moving average of TR
        if len(true_ranges) < atr_period:
            raise RuntimeError(
                f"Insufficient True Range values for {symbol} "
                f"(need {atr_period}, have {len(true_ranges)})"
            )

        # Use most recent N true ranges
        recent_trs = true_ranges[-atr_period:]
        atr_value = sum(recent_trs) / len(recent_trs)

        # Validate ATR is reasonable
        if atr_value <= 0:
            raise RuntimeError(f"Invalid ATR calculated for {symbol}: ${atr_value:.2f}")

        # Cache the result
        self._cache[cache_key] = atr_value
        logger.info(f"Calculated {atr_period}-day ATR for {symbol}: ${atr_value:.2f}")

        return atr_value

    def calculate_stop_distance(self, atr_value: float) -> float:
        """
        Calculate stop distance based on ATR multiplier from config

        Per academic paper: 10% of ATR (ATR_STOP_MULTIPLIER = 0.10)

        Args:
            atr_value: ATR value in dollars (required)

        Returns:
            Stop distance in dollars

        Raises:
            ValueError: If atr_value is invalid or config is missing
        """
        if atr_value is None or atr_value <= 0:
            raise ValueError(f"atr_value must be positive, got: {atr_value}")

        # Get and validate stop multiplier config
        stop_multiplier = self.state_manager.get_config_value(CONFIG_ATR_STOP_MULTIPLIER)
        if stop_multiplier is None:
            raise ValueError("ATR_STOP_MULTIPLIER is REQUIRED")

        # Convert to float if needed
        try:
            stop_multiplier = float(stop_multiplier)
        except (ValueError, TypeError):
            raise ValueError(f"ATR_STOP_MULTIPLIER must be a valid number, got: {stop_multiplier}")

        if stop_multiplier <= 0:
            raise ValueError(f"ATR_STOP_MULTIPLIER must be positive, got: {stop_multiplier}")

        stop_distance = atr_value * stop_multiplier

        logger.debug(f"Stop distance: ${stop_distance:.2f} (ATR ${atr_value:.2f} × {stop_multiplier})")

        return stop_distance

    @classmethod
    def clear_cache(cls):
        """
        Clear the ATR cache

        Call this at the start of a new trading day to force recalculation
        with fresh data.
        """
        cache_size = len(cls._cache)
        cls._cache.clear()
        logger.info(f"ATR cache cleared ({cache_size} entries)")

    @classmethod
    def get_cache_stats(cls) -> Dict:
        """
        Get cache statistics for monitoring/debugging

        Returns:
            Dict with cache size and entries
        """
        return {
            'size': len(cls._cache),
            'entries': list(cls._cache.keys())
        }
