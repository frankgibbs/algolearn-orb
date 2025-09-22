from src.core.command import Command
from src.core.constants import *
from src.stocks.services.stocks_strategy_service import StocksStrategyService
from src.stocks.stocks_config import STOCK_SYMBOLS, get_stock_config
from src import logger
import pytz
from datetime import datetime
from prettytable import PrettyTable

class CalculateOpeningRangeCommand(Command):
    """Calculate opening range based on CONFIG_ORB_TIMEFRAME (15/30/60 mins after market open)"""

    def execute(self, event):
        """
        Calculate opening range for all stocks in STOCK_SYMBOLS

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
            RuntimeError: If timing is invalid or configuration missing
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

        if not self._is_valid_calculation_time(now, timeframe_minutes):
            raise RuntimeError(f"Opening range calculation called at invalid time: {now} for {timeframe_minutes}m ORB")

        # Initialize service
        strategy_service = StocksStrategyService(self.application_context)

        logger.info(f"Calculating {timeframe_minutes}m opening ranges for {len(STOCK_SYMBOLS)} stocks")

        # Process each stock
        valid_ranges = []
        for symbol in STOCK_SYMBOLS:
            range_data = self._calculate_range_for_symbol(symbol, timeframe_minutes, strategy_service, now)
            if range_data:  # Only add if valid
                valid_ranges.append(range_data)

        # Send notification
        self._send_notification(valid_ranges, timeframe_minutes, now)

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

        # Fetch 1 bar matching timeframe
        bar_size = f"{timeframe_minutes} mins"
        bars = self.client.get_stock_bars(
            symbol=symbol,
            duration_minutes=timeframe_minutes,
            bar_size=bar_size,
            timeout=10
        )

        if not bars:
            raise RuntimeError(f"No bars received for {symbol}")

        # Calculate range from single bar
        range_data = strategy_service.calculate_range(bars)

        # Validate range using stock-specific config
        stock_config = get_stock_config(symbol)
        if not self._validate_range(range_data['range_size_pct'], stock_config):
            logger.info(f"Range for {symbol} ({range_data['range_size_pct']:.1f}%) outside valid bounds, skipping")
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

    def _is_valid_calculation_time(self, now, timeframe_minutes):
        """
        Check if current time is valid for opening range calculation

        Args:
            now: Current datetime in Pacific timezone (required)
            timeframe_minutes: ORB timeframe (required)

        Returns:
            Boolean indicating if timing is valid

        Raises:
            ValueError: If any parameter is None
        """
        if now is None:
            raise ValueError("now is REQUIRED")
        if timeframe_minutes is None:
            raise ValueError("timeframe_minutes is REQUIRED")

        hour = now.hour
        minute = now.minute

        # Dynamic timing based on timeframe
        if timeframe_minutes == 15:
            # 15-min ORB: Calculate at 6:45-6:50 AM PST
            return hour == 6 and 45 <= minute <= 50
        elif timeframe_minutes == 30:
            # 30-min ORB: Calculate at 7:00-7:05 AM PST
            return hour == 7 and minute <= 5
        elif timeframe_minutes == 60:
            # 60-min ORB: Calculate at 7:30-7:35 AM PST
            return hour == 7 and 30 <= minute <= 35
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe_minutes} minutes")

    def _send_notification(self, valid_ranges, timeframe_minutes, now):
        """
        Send Telegram notification with PrettyTable of valid ranges

        Args:
            valid_ranges: List of valid range dicts (required)
            timeframe_minutes: ORB timeframe (required)
            now: Current datetime (required)

        Raises:
            ValueError: If any parameter is None
        """
        if valid_ranges is None:
            raise ValueError("valid_ranges is REQUIRED")
        if timeframe_minutes is None:
            raise ValueError("timeframe_minutes is REQUIRED")
        if now is None:
            raise ValueError("now is REQUIRED")

        if not valid_ranges:
            # No valid ranges calculated
            message = f"No valid {timeframe_minutes}m opening ranges calculated"
            self.state_manager.sendTelegramMessage(message)
            return

        # Create PrettyTable
        table = PrettyTable()
        table.field_names = ["Symbol", "Range %"]
        table.align["Symbol"] = "l"
        table.align["Range %"] = "r"

        # Add rows for each valid range
        for range_data in valid_ranges:
            table.add_row([range_data['symbol'], f"{range_data['range_size_pct']:.1f}%"])

        # Send table with <pre> formatting
        message = f"<pre>{table}</pre>"
        self.state_manager.sendTelegramMessage(message)