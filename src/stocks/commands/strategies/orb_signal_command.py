from src.core.command import Command
from src.core.constants import *
from src.stocks.services.stocks_strategy_service import StocksStrategyService
from src.stocks.stocks_config import STOCK_SYMBOLS
from src.core.ibclient import IBClient
from src import logger
import pytz
from datetime import datetime, timedelta
import pandas as pd

class ORBSignalCommand(Command):
    """
    Opening Range Breakout Signal Command
    Detects breakouts and publishes EVENT_TYPE_OPEN_POSITION signals for execution
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
        # Use the IBClient instance from application context (maintains connection)
        ib_client = self.application_context.client

        logger.info(f"Analyzing {len(STOCK_SYMBOLS)} stocks for ORB breakout signals")

        # Check each stock for breakout conditions
        signals_generated = 0
        for symbol in STOCK_SYMBOLS:
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

        # Get opening range for this stock - let exception propagate
        opening_range = strategy_service.get_opening_range(symbol, now.date())
        if not opening_range:
            raise RuntimeError(f"No opening range found for {symbol}")

        # Get timeframe from configuration
        timeframe_minutes = self.state_manager.get_config_value(CONFIG_ORB_TIMEFRAME)
        if timeframe_minutes is None:
            raise ValueError("CONFIG_ORB_TIMEFRAME not configured")

        # Get previous bar data to check for breakout - let exceptions propagate
        bars_df = ib_client.get_stock_bars(
            symbol=symbol,
            duration_minutes=timeframe_minutes * 2,  # Get enough data
            bar_size=f"{timeframe_minutes} mins"
        )

        # Simple bar selection based on minute comparison
        current_minute = now.minute
        last_bar = bars_df.iloc[-1]
        last_bar_time = last_bar['date']
        last_bar_minute = last_bar_time.minute

        if current_minute == last_bar_minute:
            # We're still in the same minute/bar period
            previous_bar = bars_df.iloc[-2]
            logger.info(f"{symbol} - Current bar still in progress (minute {current_minute}), using previous bar")
        else:
            # The last bar is complete
            previous_bar = bars_df.iloc[-1]
            logger.info(f"{symbol} - Last bar complete, using bar from minute {last_bar_minute}")

        previous_close = previous_bar['close']

        # Log the range and bar being checked
        bar_time = previous_bar['date']
        logger.info(f"{symbol} - Range: ${opening_range.range_low:.2f}-${opening_range.range_high:.2f}, "
                   f"Checking bar: {bar_time}, Close: ${previous_close:.2f}")

        # Check breakout conditions: previous candle closed above/below range
        breakout_signal = self._check_breakout_signal(opening_range, previous_close)

        if breakout_signal['signal'] != 'NONE':
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

    def _check_breakout_signal(self, opening_range, previous_close):
        """
        Check if previous candle closed above/below opening range

        Args:
            opening_range: Opening range record from database
            previous_close: Previous candle close price

        Returns:
            Dict with signal info: {'signal': 'LONG'|'SHORT'|'NONE', 'entry_price': float, ...}
        """
        if previous_close > opening_range.range_high:
            # Breakout above range - LONG signal
            return {
                'signal': 'LONG',
                'entry_price': round(opening_range.range_high, 2),
                'stop_loss': round(opening_range.range_mid, 2),
                'take_profit': round(opening_range.range_high + (1.5 * opening_range.range_size), 2),
                'range_size': opening_range.range_size
            }
        elif previous_close < opening_range.range_low:
            # Breakout below range - SHORT signal
            return {
                'signal': 'SHORT',
                'entry_price': round(opening_range.range_low, 2),
                'stop_loss': round(opening_range.range_mid, 2),
                'take_profit': round(opening_range.range_low - (1.5 * opening_range.range_size), 2),
                'range_size': opening_range.range_size
            }
        else:
            # No breakout
            return {'signal': 'NONE'}

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

        # Get margin per share - will raise if fails
        margin_per_share = ib_client.get_margin_per_share(symbol)

        # Calculate how many shares we can afford with risk %
        risk_amount = account_value * (risk_pct / 100)

        # Position size = risk amount / margin per share
        quantity = int(risk_amount / margin_per_share)

        if quantity <= 0:
            raise ValueError(f"Calculated position size is {quantity} for {symbol}")

        logger.info(f"{symbol}: Margin/share=${margin_per_share:.2f}, Risk=${risk_amount:.2f}, Shares={quantity}")

        # Prepare event data
        position_data = {
            "strategy": "ORB",
            "symbol": symbol,
            "action": "BUY" if breakout_signal['signal'] == 'LONG' else "SELL",
            "quantity": quantity,
            "entry_price": breakout_signal['entry_price'],
            "stop_loss": breakout_signal['stop_loss'],
            "take_profit": breakout_signal['take_profit'],
            "range_size": breakout_signal['range_size'],
            "opening_range_id": opening_range.id,
            "reason": f"ORB breakout {breakout_signal['signal'].lower()} of range"
        }

        # Publish the event
        event = {FIELD_TYPE: EVENT_TYPE_OPEN_POSITION, FIELD_DATA: position_data}
        self.application_context.subject.notify(event)

        logger.info(f"🚀 ORB Signal Published: {position_data['action']} {symbol} @ {breakout_signal['entry_price']}")

        # Send Telegram notification
        self.state_manager.sendTelegramMessage(
            f"🚀 ORB Signal: {position_data['action']} {symbol}\n"
            f"Entry: ${breakout_signal['entry_price']:.2f}\n"
            f"Stop: ${breakout_signal['stop_loss']:.2f}\n"
            f"Target: ${breakout_signal['take_profit']:.2f}\n"
            f"Qty: {quantity} shares"
        )

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