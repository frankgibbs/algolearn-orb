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
    """
    Calculate opening range for all candidates from pre-market scan

    Enhanced for Academic ORB Strategy (Zarattini, Barbon, Aziz 2024):
    - Calculates directional bias (BULLISH/BEARISH) by comparing opening to previous close
    - Tracks opening range volume for relative volume calculations
    - Supports CONFIG_ORB_TIMEFRAME (5/15/30/60 mins after market open)
    """

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

        # Fetch previous day's close for directional bias calculation
        previous_close = self._get_previous_close(symbol)
        if previous_close is None:
            logger.warning(f"Could not get previous close for {symbol}, skipping directional bias")

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

        # Find the opening range bar using timestamp-based selection (robust approach)
        # IB returns timestamps in ET (market timezone) - market opens at 9:30 AM ET

        # Get timezone from first bar (IB provides timezone-aware timestamps)
        first_bar_time = bars.iloc[0]['date']
        bar_tz = first_bar_time.tzinfo

        # Define market open time for today in ET timezone
        # Use date from first bar to handle potential date issues
        market_date = first_bar_time.date()
        market_open_et = first_bar_time.replace(hour=9, minute=30, second=0, microsecond=0)

        # Define opening range end time based on timeframe
        opening_range_end_et = market_open_et.replace(
            minute=30 + timeframe_minutes,
            second=0,
            microsecond=0
        )

        logger.info(f"Looking for opening bar between {market_open_et} and {opening_range_end_et}")

        # Find first bar that starts at or after market open
        opening_bar = None
        opening_bar_index = None

        for i, row in bars.iterrows():
            bar_time = row['date']

            # Check if this bar is the opening range bar
            # Bar time should be >= market open and < opening range end
            if bar_time >= market_open_et and bar_time < opening_range_end_et:
                opening_bar = bars.iloc[i:i+1]
                opening_bar_index = i
                bar_timestamp = row['date']
                logger.info(f"Found opening range bar at index {i}, timestamp {bar_timestamp}")
                break

        if opening_bar is None:
            logger.warning(
                f"Cannot find opening bar for {symbol} between {market_open_et} and {opening_range_end_et}, skipping"
            )
            return None

        logger.info(f"Using opening range bar at {bar_timestamp} for {symbol}")

        # Extract opening price and volume from the bar
        opening_price = opening_bar.iloc[0]['open']
        opening_volume = int(opening_bar.iloc[0]['volume'])

        # Calculate directional bias (BULLISH if open > prev_close, BEARISH otherwise)
        directional_bias = None
        if previous_close is not None:
            if opening_price > previous_close:
                directional_bias = "BULLISH"
            elif opening_price < previous_close:
                directional_bias = "BEARISH"
            else:
                # Opening at exactly previous close - consider neutral, default to BULLISH
                directional_bias = "BULLISH"

            logger.info(
                f"Directional bias for {symbol}: {directional_bias} "
                f"(open: ${opening_price:.2f}, prev_close: ${previous_close:.2f})"
            )

        # Calculate range from opening bar only
        range_data = strategy_service.calculate_range(opening_bar)

        # Validate range using stock-specific config (or defaults for unknown symbols)
        stock_config = get_stock_config(symbol)
        if not self._validate_range(range_data['range_size_pct'], stock_config):
            logger.info(f"Range for {symbol} ({range_data['range_size_pct']:.1f}%) outside valid bounds "
                       f"({stock_config['min_range_pct']}-{stock_config['max_range_pct']}%), skipping")
            return None

        # Save valid range to database with directional bias and volume
        strategy_service.save_opening_range(
            symbol=symbol,
            date=now.date(),
            timeframe_minutes=timeframe_minutes,
            range_high=range_data['range_high'],
            range_low=range_data['range_low'],
            range_size=range_data['range_size'],
            range_size_pct=range_data['range_size_pct'],
            directional_bias=directional_bias,
            volume=opening_volume
        )

        logger.info(
            f"Opening range saved for {symbol}: "
            f"${range_data['range_low']:.2f}-${range_data['range_high']:.2f} "
            f"({range_data['range_size_pct']:.1f}%), "
            f"bias: {directional_bias}, volume: {opening_volume:,}"
        )

        # Update margin for this symbol (on-demand calculation)
        self._update_margin_for_symbol(symbol)

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

    def _update_margin_for_symbol(self, symbol):
        """
        Update margin requirement for a symbol if missing or stale

        Fetches margin from IB and saves to database. Skips if fresh margin exists (< 24 hours old).

        Args:
            symbol: Stock symbol (required)

        Raises:
            ValueError: If symbol is invalid
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        try:
            # Check if margin exists and is fresh
            margin_data = self.database_manager.get_margin(symbol)

            if margin_data:
                # Check if margin is stale (older than 24 hours)
                from datetime import datetime, timedelta
                age_hours = (datetime.now() - margin_data.last_updated).total_seconds() / 3600

                if age_hours < 24:
                    logger.debug(f"Margin for {symbol} is fresh ({age_hours:.1f}h old), skipping update")
                    return

                logger.info(f"Margin for {symbol} is stale ({age_hours:.1f}h old), updating...")

            # Fetch fresh margin from IB
            try:
                margin_per_share = self.client.get_margin_per_share(symbol)

                # Save to database
                self.database_manager.save_margin(
                    symbol=symbol,
                    margin_per_share=margin_per_share,
                    synthetic=False
                )

                logger.info(f"Updated margin for {symbol}: ${margin_per_share:.2f}/share")

            except Exception as e:
                logger.warning(f"Could not fetch margin for {symbol} from IB: {e}")
                # Don't raise - margin update is best-effort during opening range calculation

        except Exception as e:
            logger.warning(f"Error updating margin for {symbol}: {e}")
            # Don't raise - margin update shouldn't block opening range calculation

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

    def _get_previous_close(self, symbol):
        """
        Get previous day's closing price for directional bias calculation

        Args:
            symbol: Stock symbol (required)

        Returns:
            Previous day's close price, or None if unable to fetch

        Raises:
            ValueError: If symbol is None
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        try:
            # Fetch 2 days of daily bars to ensure we get yesterday's complete bar
            contract = self.client.get_stock_contract(symbol)
            bars = self.client.get_historic_data(
                contract=contract,
                history_duration="2 D",
                history_bar_size="1 day",
                timeout=10,
                whatToShow="TRADES"
            )

            if bars is None or bars.empty:
                logger.warning(f"No historical daily data for {symbol}")
                return None

            if len(bars) < 2:
                logger.warning(f"Insufficient daily data for {symbol} (need 2 days, have {len(bars)})")
                return None

            # Get yesterday's bar (second to last, since last might be incomplete today)
            yesterday_bar = bars.iloc[-2]
            previous_close = yesterday_bar['close']

            logger.debug(f"Previous close for {symbol}: ${previous_close:.2f}")
            return previous_close

        except Exception as e:
            logger.warning(f"Error fetching previous close for {symbol}: {e}")
            return None