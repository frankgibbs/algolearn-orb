from src.core.command import Command
from src.core.constants import *
from src.stocks.services.stocks_strategy_service import StocksStrategyService
from src.stocks.services.atr_service import ATRService
from src.stocks.services.relative_volume_service import RelativeVolumeService
from src.stocks.stocks_database_manager import StocksDatabaseManager
from src.core.ibclient import IBClient
from src import logger
import pytz
from datetime import datetime, timedelta
import pandas as pd

class ORBSignalCommand(Command):
    """
    Opening Range Breakout Signal Command - Academic ORB Strategy

    Enhanced implementation based on "A Profitable Day Trading Strategy for The U.S. Equity Market"
    (Zarattini, Barbon, Aziz 2024 - Swiss Finance Institute Paper No. 24-98)

    Key enhancements:
    - Directional bias filtering: Only long on BULLISH bias, only short on BEARISH bias
    - ATR-based stops: Uses 10% of 14-day ATR instead of range-based stops
    - Relative volume filtering: Only trades top N "Stocks in Play"
    - Detects breakouts and publishes EVENT_TYPE_OPEN_POSITION signals for execution
    """

    def execute(self, event):
        """
        Execute ORB strategy check

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.info("Executing ORB signal detection")

        # Get current time for bar selection
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        # Initialize services
        strategy_service = StocksStrategyService(self.application_context)
        database_manager = StocksDatabaseManager(self.application_context)
        relative_volume_service = RelativeVolumeService(self.application_context)
        # Use the IBClient instance from application context (maintains connection)
        ib_client = self.application_context.client

        # Get all candidates from today's pre-market scan
        today = now.date()
        candidates = database_manager.get_candidates(today, selected_only=False)

        if not candidates:
            logger.info("No candidates found from today's scan - skipping ORB signal detection")
            return

        logger.info(f"Found {len(candidates)} candidates from pre-market scan")

        # Get opening ranges for all candidates to extract volume data
        opening_ranges = database_manager.get_opening_ranges_by_date(today)
        if not opening_ranges:
            logger.info("No opening ranges calculated yet - run /calc-range first")
            return

        # Build candidate dict with volume from opening ranges
        candidates_with_volume = []
        for candidate in candidates:
            # Find matching opening range for this symbol
            opening_range = next((r for r in opening_ranges if r.symbol == candidate.symbol), None)
            if opening_range and opening_range.volume:
                candidates_with_volume.append({
                    'symbol': candidate.symbol,
                    'volume': opening_range.volume
                })

        if not candidates_with_volume:
            logger.info("No candidates with calculated opening range volumes yet")
            return

        # Rank by relative volume and filter to top N "Stocks in Play"
        try:
            top_candidates = relative_volume_service.rank_by_relative_volume(candidates_with_volume)
            logger.info(f"Filtered to top {len(top_candidates)} stocks by relative volume (Stocks in Play)")
        except (ValueError, RuntimeError) as e:
            logger.warning(f"Could not filter by relative volume: {e}")
            # Fall back to all candidates if relative volume filtering fails
            top_candidates = [{'symbol': c.symbol} for c in candidates]

        # Check each stock in top N for breakout conditions
        signals_generated = 0
        for candidate_data in top_candidates:
            symbol = candidate_data['symbol']
            if self._analyze_stock_for_breakout(symbol, strategy_service, ib_client, now):
                signals_generated += 1



    def _analyze_stock_for_breakout(self, symbol, strategy_service, ib_client, now):
        """
        Analyze a single stock for breakout conditions

        Args:
            symbol: Stock symbol (required)
            strategy_service: Strategy service instance (required)
            ib_client: IB client instance (required)
            now: Current datetime (required)

        Returns:
            Boolean indicating if a signal was generated

        Raises:
            ValueError: If any parameter is None
        """
        if symbol is None:
            raise ValueError("symbol is REQUIRED")
        if strategy_service is None:
            raise ValueError("strategy_service is REQUIRED")
        if ib_client is None:
            raise ValueError("ib_client is REQUIRED")
        if now is None:
            raise ValueError("now is REQUIRED")

        # Skip if symbol already has any position today (PENDING, OPEN, or CLOSED)
        if strategy_service.has_position_today(symbol):
            logger.info(f"Skipping {symbol} - already has position today")
            return False

        # Get opening range for this stock - skip symbol if not available
        try:
            opening_range = strategy_service.get_opening_range(symbol, now.date())
        except RuntimeError as e:
            logger.info(f"Skipping {symbol} - {e}")
            return False

        # Get timeframe from configuration
        timeframe_minutes = self.state_manager.get_config_value(CONFIG_ORB_TIMEFRAME)
        if timeframe_minutes is None:
            raise ValueError("CONFIG_ORB_TIMEFRAME not configured")

        # Calculate how many bars we need since opening range was established
        # Opening range ends at market open + timeframe_minutes (e.g., 6:30 AM + 30 min = 7:00 AM)
        market_open = now.replace(hour=6, minute=30, second=0, microsecond=0)
        range_end_time = market_open + timedelta(minutes=timeframe_minutes)

        # Calculate minutes since range was established
        minutes_since_range = int((now - range_end_time).total_seconds() / 60)

        # Calculate number of bars needed (add buffer for safety)
        bars_needed = max(3, (minutes_since_range // timeframe_minutes) + 2)

        # Get all bar data since opening range was established
        bars_df = ib_client.get_stock_bars(
            symbol=symbol,
            duration_minutes=bars_needed * timeframe_minutes,
            bar_size=f"{timeframe_minutes} mins"
        )

        logger.info(f"{symbol} - Fetched {len(bars_df)} bars for breakout detection")

        # Find the first breakout bar in history
        first_breakout_idx, first_breakout_bar = self._find_first_breakout_bar(bars_df, opening_range)

        # If no breakout has occurred yet, no signal
        if first_breakout_idx is None:
            logger.info(f"{symbol} - No breakout has occurred yet")
            return False

        # Determine which bar we should be checking (the "current" completed bar)
        current_minute = now.minute
        last_bar = bars_df.iloc[-1]
        last_bar_time = last_bar['date']
        last_bar_minute = last_bar_time.minute

        if current_minute == last_bar_minute:
            # We're still in the same minute/bar period, check the previous completed bar
            current_completed_bar_idx = len(bars_df) - 2
            logger.info(f"{symbol} - Current bar still in progress (minute {current_minute}), checking previous bar")
        else:
            # The last bar is complete
            current_completed_bar_idx = len(bars_df) - 1
            logger.info(f"{symbol} - Last bar complete, checking bar from minute {last_bar_minute}")

        # Only proceed if the current completed bar is the first breakout
        if current_completed_bar_idx != first_breakout_idx:
            logger.info(f"{symbol} - First breakout was at bar {first_breakout_idx}, "
                       f"current bar {current_completed_bar_idx} is not the first breakout")
            return False

        # This IS the first breakout bar! Get the actual bar data
        previous_bar = bars_df.iloc[current_completed_bar_idx]
        previous_close = previous_bar['close']

        # Log the range and bar being checked
        bar_time = previous_bar['date']
        logger.info(f"{symbol} - FIRST BREAKOUT DETECTED! Range: ${opening_range.range_low:.2f}-${opening_range.range_high:.2f}, "
                   f"Bar time: {bar_time}, Close: ${previous_close:.2f}")

        # Check breakout conditions to get signal details (direction, prices, etc.)
        breakout_signal = self._check_breakout_signal(opening_range, previous_close, symbol)

        if breakout_signal['signal'] != 'NONE':
            # Academic ORB Strategy: Volume filtering via Relative Volume already done during
            # candidate selection (Top 20 stocks with RV >= 100%). No additional volume
            # confirmation on breakout bar per academic paper methodology.

            # Check position limits before generating signal
            if not self._check_position_limits():
                logger.info(f"Position limits reached, skipping {symbol}")
                return False

            # Publish position opening signal
            self._publish_position_signal(symbol, breakout_signal, opening_range, ib_client)
            return True

        return False

    def _check_position_limits(self):
        """
        Check if we can open new positions based on configured limits

        Returns:
            Boolean indicating if new positions can be opened
        """
        max_positions = self.state_manager.get_config_value(CONFIG_MAX_POSITIONS)
        if max_positions is None:
            raise ValueError("CONFIG_MAX_POSITIONS not configured")

        # Get current open position count from database
        strategy_service = StocksStrategyService(self.application_context)
        current_positions = strategy_service.get_open_positions_count()

        return current_positions < max_positions

    def _check_breakout_signal(self, opening_range, previous_close, symbol):
        """
        Check if previous candle closed above/below opening range
        Uses real-time bid/ask for accurate entry prices

        Academic Strategy Enhancement: Applies directional bias filtering
        - Only LONG on BULLISH bias (open > previous close)
        - Only SHORT on BEARISH bias (open < previous close)

        Args:
            opening_range: Opening range record from database
            previous_close: Previous candle close price
            symbol: Stock symbol for getting real-time quotes

        Returns:
            Dict with signal info: {'signal': 'LONG'|'SHORT'|'NONE', 'entry_price': float, ...}
        """
        # Access IBClient directly from base class
        ib_client = self.application_context.client

        if previous_close > opening_range.range_high:
            # Breakout above range - potential LONG signal

            # Check directional bias - only long on BULLISH bias
            if opening_range.directional_bias != "BULLISH":
                logger.info(
                    f"{symbol} - Breakout above range but directional bias is "
                    f"{opening_range.directional_bias}, not BULLISH - skipping LONG"
                )
                return {'signal': 'NONE'}

            # MUST get real-time ASK price for buying
            contract = ib_client.get_stock_contract(symbol)
            quote = ib_client.get_stock_market_data(contract)

            if not quote or not quote.get('ask') or quote['ask'] <= 0:
                logger.warning(f"{symbol}: No ASK price available, skipping LONG signal")
                return {'signal': 'NONE'}  # Don't trade without accurate pricing

            entry_price = round(quote['ask'], 2)
            logger.info(f"{symbol} LONG: Using real-time ASK ${entry_price} (BULLISH bias confirmed)")

            # Calculate dummy take_profit (2x range size) to satisfy validation
            # Note: take_profit is not used for exits (Academic ORB uses EOD exit only)
            take_profit = entry_price + (opening_range.range_size * 2)

            return {
                'signal': 'LONG',
                'entry_price': entry_price,
                'stop_loss': self._calculate_atr_stop_loss('LONG', entry_price, symbol),
                'take_profit': take_profit,
                'range_size': opening_range.range_size
            }
        elif previous_close < opening_range.range_low:
            # Breakout below range - potential SHORT signal

            # Check directional bias - only short on BEARISH bias
            if opening_range.directional_bias != "BEARISH":
                logger.info(
                    f"{symbol} - Breakout below range but directional bias is "
                    f"{opening_range.directional_bias}, not BEARISH - skipping SHORT"
                )
                return {'signal': 'NONE'}

            # MUST get real-time BID price for selling
            contract = ib_client.get_stock_contract(symbol)
            quote = ib_client.get_stock_market_data(contract)

            if not quote or not quote.get('bid') or quote['bid'] <= 0:
                logger.warning(f"{symbol}: No BID price available, skipping SHORT signal")
                return {'signal': 'NONE'}  # Don't trade without accurate pricing

            entry_price = round(quote['bid'], 2)
            logger.info(f"{symbol} SHORT: Using real-time BID ${entry_price} (BEARISH bias confirmed)")

            # Calculate dummy take_profit (2x range size) to satisfy validation
            # Note: take_profit is not used for exits (Academic ORB uses EOD exit only)
            take_profit = entry_price - (opening_range.range_size * 2)

            return {
                'signal': 'SHORT',
                'entry_price': entry_price,
                'stop_loss': self._calculate_atr_stop_loss('SHORT', entry_price, symbol),
                'take_profit': take_profit,
                'range_size': opening_range.range_size
            }
        else:
            # No breakout
            return {'signal': 'NONE'}

    def _calculate_atr_stop_loss(self, signal_direction, entry_price, symbol):
        """
        Calculate ATR-based stop loss (Academic ORB Strategy)

        Uses 10% of 14-day ATR as stop distance per academic paper

        Args:
            signal_direction: 'LONG' or 'SHORT'
            entry_price: The entry price for the position
            symbol: Stock symbol for ATR calculation

        Returns:
            float: Stop loss price on correct side of entry

        Raises:
            ValueError: If parameters invalid or ATR calculation fails
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if signal_direction not in ['LONG', 'SHORT']:
            raise ValueError(f"signal_direction must be LONG or SHORT, got: {signal_direction}")
        if entry_price is None or entry_price <= 0:
            raise ValueError(f"entry_price must be positive, got: {entry_price}")

        # Initialize ATR service
        atr_service = ATRService(self.application_context)

        # Get ATR for symbol (uses 14-day ATR from config)
        atr_value = atr_service.get_atr(symbol, use_yesterday=True)

        # Calculate stop distance (10% of ATR per config)
        stop_distance = atr_service.calculate_stop_distance(atr_value)

        logger.info(
            f"{symbol} - ATR-based stop: ATR=${atr_value:.2f}, "
            f"Stop distance=${stop_distance:.2f} (10% ATR)"
        )

        # Calculate stop price
        if signal_direction == 'LONG':
            # For LONG, stop must be BELOW entry
            stop_loss = round(entry_price - stop_distance, 2)
            # Validate stop is below entry
            if stop_loss >= entry_price:
                raise ValueError(f"LONG stop {stop_loss} must be below entry {entry_price}")
            logger.info(f"{symbol} LONG stop: ${stop_loss:.2f} (entry ${entry_price:.2f} - stop distance ${stop_distance:.2f})")
            return stop_loss
        else:  # SHORT
            # For SHORT, stop must be ABOVE entry
            stop_loss = round(entry_price + stop_distance, 2)
            # Validate stop is above entry
            if stop_loss <= entry_price:
                raise ValueError(f"SHORT stop {stop_loss} must be above entry {entry_price}")
            logger.info(f"{symbol} SHORT stop: ${stop_loss:.2f} (entry ${entry_price:.2f} + stop distance ${stop_distance:.2f})")
            return stop_loss

    def _find_first_breakout_bar(self, bars_df, opening_range):
        """
        Find the first bar that closed outside the opening range

        Args:
            bars_df: DataFrame of historical bars
            opening_range: Opening range with range_high and range_low

        Returns:
            Tuple of (index, bar) for first breakout, or (None, None) if no breakout found
        """
        # Need at least 2 bars to detect a transition
        if len(bars_df) < 2:
            return None, None

        # Start from the second bar (index 1) to compare with previous
        for i in range(1, len(bars_df)):
            current_bar = bars_df.iloc[i]
            prev_bar = bars_df.iloc[i-1]

            # Check if previous bar was inside the range
            prev_inside = (opening_range.range_low <= prev_bar['close'] <= opening_range.range_high)

            # Check if current bar closed outside the range
            curr_outside = (current_bar['close'] > opening_range.range_high or
                          current_bar['close'] < opening_range.range_low)

            # If we found a transition from inside to outside, this is the first breakout
            if prev_inside and curr_outside:
                logger.info(f"Found first breakout at bar {i} (time: {current_bar['date']})")
                return i, current_bar

        # No breakout found in history
        return None, None

    def _publish_position_signal(self, symbol, breakout_signal, opening_range, ib_client):
        """
        Publish EVENT_TYPE_OPEN_POSITION event for execution

        Args:
            symbol: Stock symbol
            breakout_signal: Breakout signal data
            opening_range: Opening range record
            ib_client: IBClient instance from application context
        """
        # Calculate position size based on account risk AND margin
        # Get real account value from IB (no silent defaults)
        account_value = ib_client.get_pair_balance("USD")
        if account_value is None or account_value <= 0:
            raise RuntimeError(f"Cannot get account value from IB or account empty: {account_value}")
        risk_pct = self.state_manager.get_config_value(CONFIG_RISK_PERCENTAGE)
        if risk_pct is None or risk_pct <= 0:
            raise ValueError("CONFIG_RISK_PERCENTAGE is REQUIRED and must be positive")

        # Use current stock price as margin requirement for position sizing
        # This is more reliable than potentially stale/incorrect margin data from database
        # Conservative 1:1 approach (100% margin requirement)
        current_price = breakout_signal['entry_price']
        margin_per_share = current_price

        # Calculate how many shares we can afford with risk %
        risk_amount = account_value * (risk_pct / 100)

        # Position size = risk amount / margin per share (using stock price)
        quantity = int(risk_amount / margin_per_share)

        if quantity <= 0:
            raise ValueError(f"Calculated position size is {quantity} for {symbol}")

        logger.info(f"{symbol}: Using price ${current_price:.2f} as margin (1:1), Risk=${risk_amount:.2f}, Shares={quantity}")

        # Prepare event data
        position_data = {
            "strategy": "ORB",
            "symbol": symbol,
            "action": "BUY" if breakout_signal['signal'] == 'LONG' else "SELL",
            "quantity": quantity,
            "entry_price": breakout_signal['entry_price'],
            "stop_loss": breakout_signal['stop_loss'],
            "take_profit": breakout_signal['take_profit'],  # May be None for EOD exit strategy
            "range_size": breakout_signal['range_size'],
            "opening_range_id": opening_range.id,
            "reason": f"ORB breakout {breakout_signal['signal'].lower()} of range"
        }

        # Publish the event
        event = {FIELD_TYPE: EVENT_TYPE_OPEN_POSITION, FIELD_DATA: position_data}
        self.application_context.subject.notify(event)

        logger.info(f"🚀 ORB BREAKOUT Published: {position_data['action']} {symbol} @ {breakout_signal['entry_price']}")

        # Send Telegram notification (academic strategy uses EOD exit instead of take profit)
        if breakout_signal['take_profit'] is not None:
            telegram_msg = (
                f"🚀 ORB BREAKOUT: {position_data['action']} {symbol}\n"
                f"Entry: ${breakout_signal['entry_price']:.2f}\n"
                f"Stop: ${breakout_signal['stop_loss']:.2f}\n"
                f"Target: ${breakout_signal['take_profit']:.2f}\n"
                f"Qty: {quantity} shares"
            )
        else:
            telegram_msg = (
                f"🚀 ORB BREAKOUT: {position_data['action']} {symbol}\n"
                f"Entry: ${breakout_signal['entry_price']:.2f}\n"
                f"Stop: ${breakout_signal['stop_loss']:.2f} (ATR-based)\n"
                f"Exit: EOD if profitable\n"
                f"Qty: {quantity} shares"
            )

        self.state_manager.sendTelegramMessage(telegram_msg)

    def _is_valid_trading_time(self, now):
        """
        Check if current time is valid for ORB trading

        Args:
            now: Current datetime in Pacific timezone (required)

        Returns:
            Boolean indicating if timing is valid for trading

        Raises:
            ValueError: If now is None
        """
        if now is None:
            raise ValueError("now is REQUIRED")

        # Valid trading window: 7:00 AM - 12:50 PM PST (before EOD exit)
        hour = now.hour
        minute = now.minute

        # After 7:00 AM and before 12:50 PM
        if hour < 7:
            return False
        if hour > 12:
            return False
        if hour == 12 and minute >= 50:
            return False

        return True

    def _is_clock_aligned_time(self, now):
        """
        Check if current time is on a clock-aligned interval based on CONFIG_ORB_TIMEFRAME

        Args:
            now: Current datetime in Pacific timezone (required)

        Returns:
            Boolean indicating if timing is aligned
        """
        timeframe_minutes = self.state_manager.get_config_value(CONFIG_ORB_TIMEFRAME)
        if timeframe_minutes is None:
            raise ValueError("CONFIG_ORB_TIMEFRAME not configured")

        minute = now.minute

        if timeframe_minutes == 15:
            # Check at :00, :15, :30, :45
            return minute % 15 == 0
        elif timeframe_minutes == 30:
            # Check at :00, :30
            return minute % 30 == 0
        elif timeframe_minutes == 60:
            # Check at :00
            return minute == 0
        else:
            logger.warning(f"Unsupported ORB timeframe: {timeframe_minutes} minutes")
            return False