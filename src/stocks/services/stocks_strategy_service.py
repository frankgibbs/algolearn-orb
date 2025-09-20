from src import logger
from datetime import datetime, date
import pytz

class StocksStrategyService:
    """Core strategy logic and database operations for stock trading"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.client = application_context.client
        self.state_manager = application_context.state_manager
        self.database_manager = application_context.database_manager
        self.application_context = application_context

    def get_candidates(self, date, selected_only=True):
        """
        Fetch stock candidates from database for given date

        Args:
            date: Date to query (required)
            selected_only: If True, only return selected candidates

        Returns:
            List of candidate records

        Raises:
            ValueError: If date is None
            RuntimeError: If no candidates found
        """
        if date is None:
            raise ValueError("date is REQUIRED")

        logger.info(f"Fetching candidates for {date}, selected_only={selected_only}")

        candidates = self.database_manager.get_candidates(date, selected_only)

        if not candidates:
            raise RuntimeError(f"No candidates found for {date}")

        return candidates

    def save_candidates(self, candidates, scan_time):
        """
        Save stock candidates to database

        Args:
            candidates: List of candidate data (required)
            scan_time: Timestamp of scan (required)

        Raises:
            ValueError: If candidates is None or scan_time is None
        """
        if candidates is None:
            raise ValueError("candidates is REQUIRED")
        if scan_time is None:
            raise ValueError("scan_time is REQUIRED")

        logger.info(f"Saving {len(candidates)} candidates to database")

        self.database_manager.save_candidates(candidates, scan_time.date())

    def get_opening_range(self, symbol, date):
        """
        Fetch opening range from database

        Args:
            symbol: Stock symbol (required)
            date: Date to query (required)

        Returns:
            Opening range record with range_high, range_low, etc.

        Raises:
            ValueError: If symbol or date is None
            RuntimeError: If no opening range found
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if date is None:
            raise ValueError("date is REQUIRED")

        logger.info(f"Fetching opening range for {symbol} on {date}")

        opening_range = self.database_manager.get_opening_range(symbol, date)

        if opening_range is None:
            raise RuntimeError(f"No opening range found for {symbol} on {date}")

        return opening_range

    def save_opening_range(self, symbol, date, range_high, range_low, range_size, range_size_pct):
        """
        Save opening range to database

        Args:
            symbol: Stock symbol (required)
            date: Date of range (required)
            range_high: High of opening range (required)
            range_low: Low of opening range (required)
            range_size: Absolute size of range (required)
            range_size_pct: Percentage size of range (required)

        Raises:
            ValueError: If any parameter is None or invalid
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if date is None:
            raise ValueError("date is REQUIRED")
        if range_high is None:
            raise ValueError("range_high is REQUIRED")
        if range_low is None:
            raise ValueError("range_low is REQUIRED")
        if range_size is None:
            raise ValueError("range_size is REQUIRED")
        if range_size_pct is None:
            raise ValueError("range_size_pct is REQUIRED")

        # Validate range values
        if range_high <= range_low:
            raise ValueError(f"Invalid range: high ({range_high}) must be > low ({range_low})")
        if range_size <= 0:
            raise ValueError(f"Invalid range_size: {range_size}")
        if range_size_pct <= 0:
            raise ValueError(f"Invalid range_size_pct: {range_size_pct}")

        logger.info(f"Saving opening range for {symbol}: ${range_low:.2f}-${range_high:.2f} ({range_size_pct:.1f}%)")

        self.database_manager.save_opening_range(symbol, date, range_high, range_low, range_size, range_size_pct)

    def fetch_historical_bars(self, contract, duration, bar_size):
        """
        Fetch historical bars from IB

        Args:
            contract: IB contract (required)
            duration: Duration string like "30 M" (required)
            bar_size: Bar size like "1 min" (required)

        Returns:
            List of bar data

        Raises:
            ValueError: If any parameter is None
            RuntimeError: If no data received
        """
        if contract is None:
            raise ValueError("contract is REQUIRED")
        if not duration:
            raise ValueError("duration is REQUIRED")
        if not bar_size:
            raise ValueError("bar_size is REQUIRED")

        logger.info(f"Fetching {duration} of {bar_size} bars for {contract.symbol}")

        # TODO: Implement actual IB historical data request
        # Placeholder for now
        bars = []

        if not bars:
            raise RuntimeError(f"No historical data received for {contract.symbol}")

        return bars

    def calculate_range(self, bars, start_time=None, end_time=None):
        """
        Calculate high/low range from bars within time window

        Args:
            bars: List of bar data (required)
            start_time: Start time filter (optional)
            end_time: End time filter (optional)

        Returns:
            Dict with range_high, range_low, range_size, range_size_pct

        Raises:
            ValueError: If bars is None or empty
        """
        if not bars:
            raise ValueError("bars is REQUIRED and cannot be empty")

        # TODO: Implement actual range calculation
        # For now, return placeholder values
        logger.info(f"Calculating range from {len(bars)} bars")

        # Placeholder calculation
        range_high = 100.50
        range_low = 99.50
        range_size = range_high - range_low
        range_size_pct = (range_size / range_low) * 100

        return {
            'range_high': range_high,
            'range_low': range_low,
            'range_size': range_size,
            'range_size_pct': range_size_pct,
            'bar_count': len(bars)
        }

    def check_breakout_conditions(self, candidate, current_price, opening_range):
        """
        Check if stock has broken out of opening range

        Args:
            candidate: Candidate record (required)
            current_price: Current market price (required)
            opening_range: Opening range data (required)

        Returns:
            Dict with breakout info: {direction, confidence, reasoning}

        Raises:
            ValueError: If any parameter is None
        """
        if candidate is None:
            raise ValueError("candidate is REQUIRED")
        if current_price is None:
            raise ValueError("current_price is REQUIRED")
        if opening_range is None:
            raise ValueError("opening_range is REQUIRED")

        # TODO: Implement actual breakout logic
        logger.info(f"Checking breakout conditions for {candidate} at ${current_price}")

        # Placeholder logic
        return {
            'direction': 'NONE',
            'confidence': 0,
            'reasoning': 'Placeholder implementation'
        }

    def validate_market_conditions(self):
        """
        Validate current market conditions for trading

        Returns:
            Boolean indicating if conditions are favorable
        """
        # TODO: Implement market internals validation
        logger.info("Validating market conditions")

        # Placeholder - always return True for now
        return True

    def prepare_trade_parameters(self, candidate, breakout_info):
        """
        Prepare parameters for trade execution

        Args:
            candidate: Candidate record (required)
            breakout_info: Breakout analysis result (required)

        Returns:
            Dict with trade parameters

        Raises:
            ValueError: If any parameter is None
        """
        if candidate is None:
            raise ValueError("candidate is REQUIRED")
        if breakout_info is None:
            raise ValueError("breakout_info is REQUIRED")

        # TODO: Implement actual trade parameter calculation
        logger.info(f"Preparing trade parameters for {candidate}")

        # Placeholder parameters
        return {
            'symbol': 'PLACEHOLDER',
            'action': breakout_info.get('direction', 'NONE'),
            'entry_price': 100.0,
            'stop_loss': 99.0,
            'take_profit': 102.0,
            'confidence': breakout_info.get('confidence', 0)
        }