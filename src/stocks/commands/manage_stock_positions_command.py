from src.core.command import Command
from src.core.constants import *
from src import logger
import pytz
from datetime import datetime

class ManageStockPositionsCommand(Command):
    """Monitor position state transitions: PENDING → OPEN → CLOSED"""

    def execute(self, event):
        """
        Execute position status monitoring for state transitions only

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.debug("Checking position state transitions")

        # Validate market hours
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        if not self._is_market_hours(now):
            return

        # Check pending positions for fills
        self._check_pending_positions()

        # Check open positions for stop fills
        self._check_open_positions()

    def _check_pending_positions(self):
        """Check PENDING positions for order fills"""
        pending_positions = self.database_manager.get_pending_positions()

        if not pending_positions:
            logger.debug("No pending positions to check")
            return

        logger.info(f"Checking {len(pending_positions)} pending positions")

        for position in pending_positions:
            self._check_position_fill(position)

    def _check_open_positions(self):
        """Check OPEN positions for stop order fills"""
        open_positions = self.database_manager.get_open_positions()

        if not open_positions:
            logger.debug("No open positions to check")
            return

        logger.info(f"Checking {len(open_positions)} open positions")

        for position in open_positions:
            self._check_stop_fill(position)

    def _check_position_fill(self, position):
        """
        Check if a pending position's parent order has been filled

        Args:
            position: Position record (required)

        Raises:
            ValueError: If position is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")

        logger.debug(f"Checking parent order fill for position {position.id}")

        # Get order status from IB
        order_status = self.client.get_order_by_id(position.id)

        if order_status and order_status.get('status') == 'Filled':
            fill_price = order_status.get('avgFillPrice', 0.0)
            fill_time = order_status.get('fillTime')

            # Transition to OPEN
            self._transition_to_open(position, fill_price, fill_time)

    def _check_stop_fill(self, position):
        """
        Check if an open position's stop order has been filled

        Args:
            position: Position record (required)

        Raises:
            ValueError: If position is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")

        logger.debug(f"Checking stop order fill for position {position.id}")

        # Get stop order status from IB
        stop_order_status = self.client.get_order_by_id(position.stop_order_id)

        if stop_order_status and stop_order_status.get('status') == 'Filled':
            exit_price = stop_order_status.get('avgFillPrice', 0.0)
            exit_time = stop_order_status.get('fillTime')

            # Transition to CLOSED
            self._transition_to_closed(position, exit_price, exit_time, "STOP_LOSS")

    def _transition_to_open(self, position, fill_price, fill_time):
        """
        Transition position from PENDING to OPEN

        Args:
            position: Position record (required)
            fill_price: Fill price from IB (required)
            fill_time: Fill time from IB (required)

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if fill_price is None:
            raise ValueError("fill_price is REQUIRED")

        logger.info(f"Position {position.id} ({position.symbol}) filled at ${fill_price}")

        # Update position to OPEN status
        self.database_manager.update_position_status(
            position.id,
            'OPEN',
            entry_price=fill_price,
            entry_time=fill_time
        )

        # Send notification
        direction = "📈 LONG" if position.direction == 'LONG' else "📉 SHORT"
        self.state_manager.sendTelegramMessage(
            f"✅ Position OPEN: {direction} {position.symbol} @ ${fill_price}"
        )

    def _transition_to_closed(self, position, exit_price, exit_time, exit_reason):
        """
        Transition position from OPEN to CLOSED

        Args:
            position: Position record (required)
            exit_price: Exit price from IB (required)
            exit_time: Exit time from IB (required)
            exit_reason: Reason for exit (required)

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if exit_price is None:
            raise ValueError("exit_price is REQUIRED")
        if not exit_reason:
            raise ValueError("exit_reason is REQUIRED")

        logger.info(f"Position {position.id} ({position.symbol}) closed at ${exit_price}")

        # Calculate realized P&L
        realized_pnl = self._calculate_realized_pnl(position, exit_price)

        # Update position to CLOSED status
        self.database_manager.update_position_status(
            position.id,
            'CLOSED',
            exit_price=exit_price,
            exit_time=exit_time,
            exit_reason=exit_reason,
            realized_pnl=realized_pnl
        )

        # Send notification
        pnl_emoji = "🟢" if realized_pnl >= 0 else "🔴"
        self.state_manager.sendTelegramMessage(
            f"🔚 Position CLOSED: {position.symbol} @ ${exit_price} | "
            f"P&L: {pnl_emoji} ${realized_pnl:.2f} | Reason: {exit_reason}"
        )

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
        Check if we're in market hours for position management

        Args:
            now: Current datetime in Pacific timezone (required)

        Returns:
            Boolean indicating if it's market hours

        Raises:
            ValueError: If now is None
        """
        if now is None:
            raise ValueError("now is REQUIRED")

        # Manage positions during extended hours: 6:30 AM - 1:00 PM PST
        hour = now.hour
        minute = now.minute

        if hour < 6 or (hour == 6 and minute < 30) or hour >= 13:
            return False

        # Check weekday
        return now.weekday() < 5