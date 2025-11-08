from src.core.command import Command
from src.core.constants import *
from src.stocks.services.atr_service import ATRService
from src.stocks.services.position_service import PositionService
from src import logger
import pytz
from datetime import datetime

class MoveStopOrderCommand(Command):
    """
    Handle trailing stop order modifications - Academic ORB Strategy

    Enhanced for "A Profitable Day Trading Strategy for The U.S. Equity Market"
    (Zarattini, Barbon, Aziz 2024):
    - Uses ATR-based trailing stops instead of range-based
    - Trails using 10% of 14-day ATR
    - Always active (no profit threshold to activate)
    """

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
        Calculate new ATR-based trailing stop price if conditions are met

        Academic Strategy: Uses 10% of 14-day ATR for trailing distance
        Always active (no profit threshold), trails from entry

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
        if current_price is None or current_price <= 0:
            raise ValueError(f"current_price must be positive, got: {current_price}")

        # Initialize ATR service
        atr_service = ATRService(self.application_context)

        # Get ATR for this symbol
        try:
            atr_value = atr_service.get_atr(position.symbol, use_yesterday=True)
            stop_distance = atr_service.calculate_stop_distance(atr_value)
        except (ValueError, RuntimeError) as e:
            logger.warning(f"Could not calculate ATR for {position.symbol}: {e}")
            return None

        # Calculate potential new stop based on ATR
        if position.direction == 'LONG':
            # For LONG, trail below current price by ATR distance
            potential_stop = current_price - stop_distance
        else:  # SHORT
            # For SHORT, trail above current price by ATR distance
            potential_stop = current_price + stop_distance

        potential_stop = round(potential_stop, 2)

        # Get current stop (either initial stop or already-moved trailing stop)
        current_stop = position.trailing_stop_price if position.stop_moved else position.stop_loss

        # Only move stop in favorable direction (tighter, never looser)
        if position.direction == 'LONG':
            # For LONG, only move stop UP (higher)
            if potential_stop > current_stop:
                logger.info(
                    f"{position.symbol} LONG trailing: ${current_stop:.2f} → ${potential_stop:.2f} "
                    f"(ATR-based, distance: ${stop_distance:.2f})"
                )
                return potential_stop
        else:  # SHORT
            # For SHORT, only move stop DOWN (lower)
            if potential_stop < current_stop:
                logger.info(
                    f"{position.symbol} SHORT trailing: ${current_stop:.2f} → ${potential_stop:.2f} "
                    f"(ATR-based, distance: ${stop_distance:.2f})"
                )
                return potential_stop

        # No improvement in stop position
        logger.debug(f"{position.symbol} - No stop movement (potential: ${potential_stop:.2f}, current: ${current_stop:.2f})")
        return None

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
            position_service = PositionService(self.application_context)
            locked_pnl = position_service.calculate_pnl(position, new_stop_price)

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