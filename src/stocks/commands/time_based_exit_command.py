from src.core.command import Command
from src.core.constants import *
from src import logger
import pytz
from datetime import datetime, timedelta

class TimeBasedExitCommand(Command):
    """Handle time-based exits for stagnant positions"""

    def execute(self, event):
        """
        Execute time-based exit checks for all open positions

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.debug("Checking for time-based exits")

        # Validate market hours
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        if not self._is_market_hours(now):
            return

        # Get all open positions
        open_positions = self.database_manager.get_open_positions()

        if not open_positions:
            logger.debug("No open positions for time-based exit check")
            return

        logger.info(f"Checking time-based exits for {len(open_positions)} positions")

        # Process each position for stagnation
        for position in open_positions:
            self._check_position_stagnation(position, now)

    def _check_position_stagnation(self, position, now):
        """
        Check if position should be closed due to stagnation

        Args:
            position: Position record (required)
            now: Current datetime (required)

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if now is None:
            raise ValueError("now is REQUIRED")

        logger.debug(f"Checking stagnation for position {position.id} ({position.symbol})")

        # Calculate how long position has been open
        if not position.entry_time:
            logger.warning(f"Position {position.id} has no entry_time, skipping")
            return

        time_open = now - position.entry_time
        minutes_open = time_open.total_seconds() / 60

        # Get stagnation threshold from configuration
        stagnation_threshold = self.state_manager.get_config_value(CONFIG_STAGNATION_THRESHOLD_MINUTES)
        if stagnation_threshold is None:
            raise ValueError("CONFIG_STAGNATION_THRESHOLD_MINUTES is REQUIRED")

        if minutes_open > stagnation_threshold:
            # Get current price to check if position is stagnant
            current_price = self.client.get_stock_price(position.symbol)
            if not current_price:
                logger.warning(f"Could not get current price for {position.symbol}")
                return

            if self._is_position_stagnant(position, current_price):
                self._close_stagnant_position(position, current_price)

    def _is_position_stagnant(self, position, current_price):
        """
        Determine if position is stagnant (no significant movement)

        Args:
            position: Position record (required)
            current_price: Current market price (required)

        Returns:
            Boolean indicating if position is stagnant

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if current_price is None:
            raise ValueError("current_price is REQUIRED")

        # Calculate price movement as percentage
        price_change_pct = abs(current_price - position.entry_price) / position.entry_price * 100

        # Consider stagnant if movement is less than 25% of range size
        stagnation_threshold = (position.range_size / position.entry_price) * 100 * 0.25

        is_stagnant = price_change_pct < stagnation_threshold

        if is_stagnant:
            logger.info(f"Position {position.symbol} is stagnant: "
                       f"movement {price_change_pct:.2f}% < threshold {stagnation_threshold:.2f}%")

        return is_stagnant

    def _close_stagnant_position(self, position, current_price):
        """
        Close a stagnant position with market order

        Args:
            position: Position record (required)
            current_price: Current market price (required)

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if current_price is None:
            raise ValueError("current_price is REQUIRED")

        logger.info(f"Converting stop order to market order for stagnant position {position.id} ({position.symbol})")

        # Convert stop order to market order for immediate execution
        success = self.client.convert_stop_to_market(position.stop_order_id)

        if success:
            # Update position exit reason in database for tracking
            self.database_manager.update_position_status(
                position.id,
                'OPEN',  # Status stays OPEN until ManageStockPositionsCommand detects fill
                exit_reason="TIME_EXIT_STAGNANT"  # Track why we initiated the exit
            )

            # Send notification that exit was initiated
            self.state_manager.sendTelegramMessage(
                f"⏱️ TIME EXIT initiated: {position.symbol} - converting stop to market order (>90min stagnant)"
            )

            logger.info(f"Stop order converted to market for position {position.id}")
        else:
            logger.error(f"Failed to convert stop order for stagnant position {position.id}")

    def _calculate_realized_pnl(self, position, exit_price):
        """
        Calculate realized P&L for a position

        Args:
            position: Position record (required)
            exit_price: Exit price (required)

        Returns:
            Realized P&L as float

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if exit_price is None:
            raise ValueError("exit_price is REQUIRED")

        if position.direction == 'LONG':
            return (exit_price - position.entry_price) * position.shares
        else:  # SHORT
            return (position.entry_price - exit_price) * position.shares

    def _is_market_hours(self, now):
        """
        Check if we're in market hours for time-based exits

        Args:
            now: Current datetime in Pacific timezone (required)

        Returns:
            Boolean indicating if it's market hours

        Raises:
            ValueError: If now is None
        """
        if now is None:
            raise ValueError("now is REQUIRED")

        # Check time exits during extended hours: 6:30 AM - 1:00 PM PST
        hour = now.hour
        minute = now.minute

        if hour < 6 or (hour == 6 and minute < 30) or hour >= 13:
            return False

        # Check weekday
        return now.weekday() < 5