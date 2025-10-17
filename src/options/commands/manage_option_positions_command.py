from src.core.command import Command
from src.core.constants import *
from src import logger
import pytz
import time
from datetime import datetime


class ManageOptionPositionsCommand(Command):
    """Monitor option position state transitions: PENDING → OPEN → CLOSED"""

    def execute(self, event):
        """
        Execute option position status monitoring for state transitions

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.debug("Checking option position state transitions")

        # Validate market hours
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        if not self._is_market_hours(now):
            return

        # Check pending option positions for fills
        self._check_pending_positions()

        # Check closing orders for fills
        self._check_closing_positions()

    def _check_pending_positions(self):
        """Check PENDING option positions for combo order fills"""
        option_db_manager = self.application_context.option_db_manager
        pending_positions = option_db_manager.get_all_positions(days_back=7)
        pending_positions = [p for p in pending_positions if p.status == "PENDING"]

        if not pending_positions:
            logger.debug("No pending option positions to check")
            return

        logger.info(f"Checking {len(pending_positions)} pending option positions")

        for position in pending_positions:
            self._check_position_fill(position)
            # Small delay to avoid overwhelming IB
            time.sleep(0.1)

    def _check_closing_positions(self):
        """Check OPEN positions with closing orders pending"""
        option_db_manager = self.application_context.option_db_manager

        # Get all OPEN positions
        open_positions = option_db_manager.get_open_positions()

        # Filter: only those with closing_order_id != 0
        closing_positions = [p for p in open_positions if p.closing_order_id != 0]

        if not closing_positions:
            logger.debug("No closing orders to check")
            return

        logger.info(f"Checking {len(closing_positions)} closing orders")

        for position in closing_positions:
            self._check_closing_order_fill(position)
            # Small delay to avoid overwhelming IB
            time.sleep(0.1)

    def _check_position_fill(self, position):
        """
        Check if a pending option position's combo order has been filled

        Args:
            position: OptionPosition record (required)

        Raises:
            ValueError: If position is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")

        logger.debug(f"Checking combo order {position.id} for {position.symbol} {position.strategy_type}")

        # Check for fills - combo orders have single order ID
        fill_info = self.client.get_fills_by_order_id(position.id, timeout=5)

        if fill_info:
            # For combo orders, use the net credit/debit from position record
            # This is the limit price that IB confirmed when the order filled
            fill_price = position.net_credit

            # Log fill_info for debugging (note: aggregates individual leg fills incorrectly for combos)
            if fill_info.get('lmtPrice') is not None:
                logger.debug(f"Fill info lmtPrice: ${fill_info.get('lmtPrice'):.2f} (aggregated from legs, not used)")

            if fill_price is None or fill_price == 0:
                raise RuntimeError(
                    f"Combo order {position.id} filled but position.net_credit is invalid: {fill_price}. "
                    f"This indicates a problem with order placement or database record."
                )

            fill_time = datetime.now()

            logger.info(f"Option position {position.id} ({position.symbol} {position.strategy_type}) filled at ${fill_price}")

            # Transition to OPEN
            self._transition_to_open(position, fill_price, fill_time)

    def _check_closing_order_fill(self, position):
        """
        Check if a closing order has been filled

        Args:
            position: OptionPosition record with closing_order_id != 0 (required)

        Raises:
            ValueError: If position is None or closing_order_id is 0
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if position.closing_order_id == 0:
            raise ValueError("position.closing_order_id must be != 0")

        logger.debug(f"Checking closing order {position.closing_order_id} for position {position.id}")

        # Check for fills on closing order
        fill_info = self.client.get_fills_by_order_id(position.closing_order_id, timeout=5)

        if fill_info:
            # STRICT: Must have valid lmtPrice
            exit_value = fill_info.get('lmtPrice')
            if exit_value is None:
                raise RuntimeError(
                    f"Closing order {position.closing_order_id} filled but lmtPrice is None. "
                    f"Cannot calculate realized P&L - will not proceed."
                )

            fill_time = datetime.now()

            # Calculate realized P&L
            if position.is_credit_spread:
                # Credit spread: profit = credit - closing cost
                realized_pnl = (position.net_credit * 100) - (exit_value * 100)
            else:
                # Debit spread: profit = closing value - debit paid
                realized_pnl = (exit_value * 100) - abs(position.net_credit * 100)

            logger.info(f"Closing order {position.closing_order_id} filled at ${exit_value:.2f}, P&L: ${realized_pnl:.2f}")

            # Transition to CLOSED
            self._transition_to_closed(position, exit_value, realized_pnl, fill_time)

    def _transition_to_open(self, position, fill_price, fill_time):
        """
        Transition option position from PENDING to OPEN

        Args:
            position: OptionPosition record (required)
            fill_price: Fill price from IB (required)
            fill_time: Fill time (required)

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if fill_price is None:
            raise ValueError("fill_price is REQUIRED")

        logger.info(f"Option position {position.id} ({position.symbol} {position.strategy_type}) filled at ${fill_price}")

        # Update position to OPEN status
        option_db_manager = self.application_context.option_db_manager
        option_db_manager.update_position_status(
            position.id,
            'OPEN',
            entry_price=fill_price
        )

        # Build leg details for notification
        legs_text = "\n".join([
            f"  {leg.action} {leg.quantity}x {leg.strike}{leg.right}"
            for leg in position.legs
        ])

        # Calculate ROI metrics
        roi_target = (position.max_profit / position.max_risk * 100) if position.max_risk > 0 else 0

        # Send detailed notification
        message = (
            f"✅ Option Position FILLED\n"
            f"Symbol: {position.symbol}\n"
            f"Strategy: {position.strategy_type}\n"
            f"Fill Price: ${fill_price:.2f}\n"
            f"Max Profit: ${position.max_profit:.2f}\n"
            f"Max Risk: ${position.max_risk:.2f}\n"
            f"ROI Target: {roi_target:.1f}%\n"
            f"DTE: {position.days_to_expiration}\n"
            f"Legs:\n{legs_text}\n"
            f"Order ID: {position.id}"
        )

        self.state_manager.sendTelegramMessage(message)
        logger.info(f"Fill notification sent for option position {position.id}")

    def _transition_to_closed(self, position, exit_value, realized_pnl, fill_time):
        """
        Transition option position from OPEN to CLOSED

        Args:
            position: OptionPosition record (required)
            exit_value: Closing price from IB (required)
            realized_pnl: Final profit/loss (required)
            fill_time: Fill time (required)

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if exit_value is None:
            raise ValueError("exit_value is REQUIRED")
        if realized_pnl is None:
            raise ValueError("realized_pnl is REQUIRED")

        logger.info(f"Option position {position.id} ({position.symbol} {position.strategy_type}) closing at ${exit_value:.2f}, P&L: ${realized_pnl:.2f}")

        # Update position to CLOSED status
        option_db_manager = self.application_context.option_db_manager
        option_db_manager.close_position(
            order_id=position.id,
            exit_value=exit_value,
            exit_reason=position.exit_reason,
            realized_pnl=realized_pnl
        )

        # Calculate actual ROI
        actual_roi = (realized_pnl / position.max_risk * 100) if position.max_risk > 0 else 0

        # Send notification
        pnl_emoji = "✅" if realized_pnl > 0 else "❌"
        message = (
            f"{pnl_emoji} Option Position CLOSED\n"
            f"Symbol: {position.symbol}\n"
            f"Strategy: {position.strategy_type}\n"
            f"Exit Price: ${exit_value:.2f}\n"
            f"Realized P&L: ${realized_pnl:.2f}\n"
            f"Actual ROI: {actual_roi:.1f}%\n"
            f"Exit Reason: {position.exit_reason}\n"
            f"Position ID: {position.id}"
        )

        self.state_manager.sendTelegramMessage(message)
        logger.info(f"Close notification sent for option position {position.id}")

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
