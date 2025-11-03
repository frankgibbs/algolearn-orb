from src.core.command import Command
from src.core.constants import *
from src import logger
import pytz
from datetime import datetime

class MoveStopOrderCommand(Command):
    """Handle trailing stop order modifications"""

    def execute(self, event):
        """
        Execute trailing stop management for all open positions

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.debug("Checking for trailing stop updates")

        # Validate market hours
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        if not self._is_market_hours(now):
            return

        # Get all open positions
        open_positions = self.database_manager.get_open_positions()

        if not open_positions:
            logger.debug("No open positions for stop management")
            return

        logger.info(f"Checking trailing stops for {len(open_positions)} positions")

        # Process each position for stop updates
        for position in open_positions:
            self._manage_position_stop(position)

    def _manage_position_stop(self, position):
        """
        Manage trailing stop for a single position

        Args:
            position: Position record (required)

        Raises:
            ValueError: If position is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")

        logger.debug(f"Checking stop for position {position.id} ({position.symbol})")

        # Get current market price
        current_price = self.client.get_stock_price(position.symbol)
        if not current_price:
            logger.warning(f"Could not get current price for {position.symbol}")
            return

        # Check if stop should be moved
        new_stop_price = self._calculate_new_stop_price(position, current_price)

        if new_stop_price:
            self._move_stop_order(position, new_stop_price)

    def _calculate_new_stop_price(self, position, current_price):
        """
        Calculate new trailing stop price if conditions are met

        Args:
            position: Position record (required)
            current_price: Current market price (required)

        Returns:
            New stop price if stop should be moved, None otherwise

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if current_price is None:
            raise ValueError("current_price is REQUIRED")

        # Get trailing stop ratio from config
        trailing_ratio = self.state_manager.get_config_value(CONFIG_TRAILING_STOP_RATIO)

        # If not trailing yet, check if take profit level reached
        if not position.stop_moved:
            if self._should_activate_trailing(position, current_price):
                # Activate trailing stop
                if position.direction == 'LONG':
                    new_stop = current_price - (position.range_size * trailing_ratio)
                else:  # SHORT
                    new_stop = current_price + (position.range_size * trailing_ratio)

                logger.info(f"Activating trailing stop for {position.symbol} at ${new_stop:.2f}")
                return round(new_stop, 2)
        else:
            # Already trailing, check if we can move stop further
            current_stop = position.trailing_stop_price  # Always populated now, no fallback needed

            if position.direction == 'LONG':
                potential_stop = current_price - (position.range_size * trailing_ratio)
                if potential_stop > current_stop:
                    logger.info(f"Moving trailing stop higher for {position.symbol}: ${current_stop:.2f} → ${potential_stop:.2f}")
                    return round(potential_stop, 2)
            else:  # SHORT
                potential_stop = current_price + (position.range_size * trailing_ratio)
                if potential_stop < current_stop:
                    logger.info(f"Moving trailing stop lower for {position.symbol}: ${current_stop:.2f} → ${potential_stop:.2f}")
                    return round(potential_stop, 2)

        return None

    def _should_activate_trailing(self, position, current_price):
        """
        Check if profit level has been reached to activate trailing
        Uses CONFIG_TRAILING_STOP_RATIO to determine activation level

        Args:
            position: Position record (required)
            current_price: Current market price (required)

        Returns:
            Boolean indicating if trailing should be activated

        Raises:
            ValueError: If any parameter is None or config missing
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if current_price is None:
            raise ValueError("current_price is REQUIRED")

        # Get trailing ratio to determine activation level
        trailing_ratio = self.state_manager.get_config_value(CONFIG_TRAILING_STOP_RATIO)
        if trailing_ratio is None:
            raise ValueError("CONFIG_TRAILING_STOP_RATIO is REQUIRED")

        if position.direction == 'LONG':
            # Activate when profit reaches trailing_ratio × range (e.g., 0.5x)
            activation_price = position.entry_price + (position.range_size * trailing_ratio)
            return current_price >= activation_price
        else:  # SHORT
            # Activate when profit reaches trailing_ratio × range
            activation_price = position.entry_price - (position.range_size * trailing_ratio)
            return current_price <= activation_price

    def _move_stop_order(self, position, new_stop_price):
        """
        Execute stop order modification via IB

        Args:
            position: Position record (required)
            new_stop_price: New stop price (required)

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if new_stop_price is None:
            raise ValueError("new_stop_price is REQUIRED")

        logger.info(f"Moving stop order {position.stop_order_id} to ${new_stop_price:.2f}")

        # Call IB to modify stop order
        success = self.client.modify_stop_order(position.stop_order_id, new_stop_price)

        if success:
            # Update database
            self.database_manager.update_position_status(
                position.id,
                'OPEN',  # Status stays OPEN
                stop_moved=True,
                trailing_stop_price=new_stop_price
            )

            # Calculate locked P&L (worst case exit at new stop)
            if position.direction == 'LONG':
                locked_pnl = (new_stop_price - position.entry_price) * position.shares
            else:  # SHORT
                locked_pnl = (position.entry_price - new_stop_price) * position.shares

            # Send notification with locked value
            action = "🔼 Raised" if position.direction == 'LONG' else "🔽 Lowered"
            locked_sign = "+" if locked_pnl >= 0 else ""
            self.state_manager.sendTelegramMessage(
                f"🎯 {action} trailing stop: {position.symbol} → ${new_stop_price:.2f} (Locked: {locked_sign}${locked_pnl:.2f})"
            )
        else:
            logger.error(f"Failed to modify stop order {position.stop_order_id}")

    def _is_market_hours(self, now):
        """
        Check if we're in market hours for stop management

        Args:
            now: Current datetime in Pacific timezone (required)

        Returns:
            Boolean indicating if it's market hours

        Raises:
            ValueError: If now is None
        """
        if now is None:
            raise ValueError("now is REQUIRED")

        # Manage stops during extended hours: 6:30 AM - 1:00 PM PST
        hour = now.hour
        minute = now.minute

        if hour < 6 or (hour == 6 and minute < 30) or hour >= 13:
            return False

        # Check weekday
        return now.weekday() < 5