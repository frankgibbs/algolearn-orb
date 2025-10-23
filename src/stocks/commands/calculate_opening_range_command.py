from src.core.command import Command
from src.core.constants import *
from src.stocks.services.stocks_strategy_service import StocksStrategyService
from src.stocks.stocks_config import get_stock_config
from src.stocks.stocks_database_manager import StocksDatabaseManager
from src import logger
import pytz
from datetime import datetime, time
from prettytable import PrettyTable

class CalculateOpeningRangeCommand(Command):
    """Calculate opening range for all candidates from pre-market scan based on CONFIG_ORB_TIMEFRAME (15/30/60 mins after market open)"""

    def execute(self, event):
        """
        Calculate opening range for all candidates from today's pre-market scan

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
            RuntimeError: If timing is invalid, configuration missing, or no scan results found
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.info("Calculating opening ranges for ORB strategy")

        # Validate timing
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        # Get timeframe from config
        timeframe_minutes = self.state_manager.get_config_value(CONFIG_ORB_TIMEFRAME)
        if timeframe_minutes is None:
            raise ValueError("CONFIG_ORB_TIMEFRAME not configured")

        # Initialize services
        strategy_service = StocksStrategyService(self.application_context)
        database_manager = StocksDatabaseManager(self.application_context)

        # Get all candidates from today's pre-market scan
        today = now.date()
        candidates = database_manager.get_candidates(today, selected_only=False)

        if not candidates:
            raise RuntimeError(
                "No candidates found for today. "
                "Run the pre-market scan (/scan) first to identify trading candidates."
            )

        logger.info(f"Calculating {timeframe_minutes}m opening ranges for {len(candidates)} candidates from scan")

        # Process each candidate from scan
        valid_ranges = []
        for candidate in candidates:
            symbol = candidate.symbol
            range_data = self._calculate_range_for_symbol(symbol, timeframe_minutes, strategy_service, now)
            if range_data:  # Only add if valid
                valid_ranges.append(range_data)

        # Send notification
        self._send_notification(valid_ranges, strategy_service)

    def _calculate_range_for_symbol(self, symbol, timeframe_minutes, strategy_service, now):
        """
        Calculate opening range for a single symbol

        Args:
            symbol: Stock symbol (required)
            timeframe_minutes: Timeframe in minutes (required)
            strategy_service: Strategy service instance (required)
            now: Current datetime (required)

        Returns:
            Dict with symbol and range_size_pct if valid, None if invalid

        Raises:
            ValueError: If any parameter is None
            RuntimeError: If data fetch or calculation fails
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if timeframe_minutes is None:
            raise ValueError("timeframe_minutes is REQUIRED")
        if strategy_service is None:
            raise ValueError("strategy_service is REQUIRED")
        if now is None:
            raise ValueError("now is REQUIRED")

        logger.info(f"Calculating {timeframe_minutes}m opening range for {symbol}")

        # Calculate market open time for today in Pacific Time (6:30 AM PST = 9:30 AM ET)
        pacific_tz = pytz.timezone('US/Pacific')
        today_date = now.date()
        market_open_pst = pacific_tz.localize(datetime.combine(today_date, time(hour=6, minute=30)))

        # Ensure we're working in PST
        now_pst = now if now.tzinfo else pacific_tz.localize(now)

        # Calculate minutes elapsed since market open
        if now_pst < market_open_pst:
            raise RuntimeError(f"Market has not opened yet. Current time: {now_pst}, Market opens: {market_open_pst}")

        minutes_since_open = int((now_pst - market_open_pst).total_seconds() / 60)

        # Request enough historical data to cover from market open to now
        # Add buffer to ensure we get the opening range bar
        duration_minutes = max(minutes_since_open + timeframe_minutes, timeframe_minutes * 2)

        logger.info(f"Market opened {minutes_since_open} minutes ago, requesting {duration_minutes} minutes of data")

        # Fetch historical bars with sufficient duration
        bar_size = f"{timeframe_minutes} mins"
        bars = self.client.get_stock_bars(
            symbol=symbol,
            duration_minutes=duration_minutes,
            bar_size=bar_size,
            timeout=10
        )

        # Extract the first bar (opening range) from the historical data
        if bars.empty:
            raise RuntimeError(f"No historical data received for {symbol}")

        # Debug: log all bar timestamps to understand what IB is returning
        logger.info(f"Received {len(bars)} bars for {symbol}:")
        for i, row in bars.iterrows():
            logger.info(f"  Bar {i}: {row['date']} - OHLC: {row['open']:.2f}/{row['high']:.2f}/{row['low']:.2f}/{row['close']:.2f}")

        # Find the opening range bar by counting backwards from the last bar
        last_bar = bars.iloc[-1]
        last_bar_time = last_bar['date']

        # Assume timestamps are in ET (market timezone)
        # Market opens at 9:30 AM ET
        market_open_time = last_bar_time.replace(hour=9, minute=30, second=0, microsecond=0)

        # Calculate minutes from market open to last bar
        minutes_from_open = int((last_bar_time - market_open_time).total_seconds() / 60)

        # Calculate how many bars since market open
        bars_since_open = minutes_from_open // timeframe_minutes

        # The opening bar index (counting backwards from last bar)
        opening_bar_index = len(bars) - bars_since_open - 1

        logger.info(f"Last bar at {last_bar_time}, {minutes_from_open} minutes from market open")
        logger.info(f"Opening bar should be at index {opening_bar_index} ({bars_since_open} bars back)")

        if opening_bar_index < 0 or opening_bar_index >= len(bars):
            logger.warning(f"Cannot find opening bar for {symbol}: calculated index {opening_bar_index} out of range (0-{len(bars)-1}), skipping")
            return None

        opening_bar = bars.iloc[opening_bar_index:opening_bar_index+1]
        bar_timestamp = opening_bar.iloc[0]['date']
        logger.info(f"Using opening range bar at {bar_timestamp} for {symbol}")

        # Calculate range from opening bar only
        range_data = strategy_service.calculate_range(opening_bar)

        # Validate range using stock-specific config (or defaults for unknown symbols)
        stock_config = get_stock_config(symbol)
        if not self._validate_range(range_data['range_size_pct'], stock_config):
            logger.info(f"Range for {symbol} ({range_data['range_size_pct']:.1f}%) outside valid bounds "
                       f"({stock_config['min_range_pct']}-{stock_config['max_range_pct']}%), skipping")
            return None

        # Save valid range to database
        strategy_service.save_opening_range(
            symbol=symbol,
            date=now.date(),
            timeframe_minutes=timeframe_minutes,
            range_high=range_data['range_high'],
            range_low=range_data['range_low'],
            range_size=range_data['range_size'],
            range_size_pct=range_data['range_size_pct']
        )

        logger.info(f"Opening range saved for {symbol}: "
                   f"${range_data['range_low']:.2f}-${range_data['range_high']:.2f} "
                   f"({range_data['range_size_pct']:.1f}%)")

        return {
            'symbol': symbol,
            'range_size_pct': range_data['range_size_pct']
        }

    def _validate_range(self, range_size_pct, stock_config):
        """
        Validate if range size is within acceptable bounds

        Args:
            range_size_pct: Range size as percentage (required)
            stock_config: Stock configuration dict (required)

        Returns:
            Boolean indicating if range is valid

        Raises:
            ValueError: If any parameter is None
        """
        if range_size_pct is None:
            raise ValueError("range_size_pct is REQUIRED")
        if stock_config is None:
            raise ValueError("stock_config is REQUIRED")

        min_pct = stock_config['min_range_pct']
        max_pct = stock_config['max_range_pct']

        return min_pct <= range_size_pct <= max_pct

    def _send_notification(self, valid_ranges, strategy_service):
        """
        Send Telegram notification with formatted table of valid ranges

        Args:
            valid_ranges: List of valid range dicts (required)
            strategy_service: Strategy service instance (required)

        Raises:
            ValueError: If any parameter is None
        """
        if valid_ranges is None:
            raise ValueError("valid_ranges is REQUIRED")
        if strategy_service is None:
            raise ValueError("strategy_service is REQUIRED")

        if not valid_ranges:
            # No valid ranges calculated
            message = "No valid opening ranges calculated"
            self.state_manager.sendTelegramMessage(message)
            return

        # Use shared formatting method
        message = strategy_service.format_ranges_table(valid_ranges)
        self.state_manager.sendTelegramMessage(message)