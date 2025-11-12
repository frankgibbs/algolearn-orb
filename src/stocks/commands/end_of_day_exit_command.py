from src.core.command import Command
from src.core.constants import *
from src.stocks.services.position_service import PositionService
from src import logger
import pytz
from datetime import datetime

class EndOfDayExitCommand(Command):
    """
    Handle end-of-day position closure and daily reporting - Academic ORB Strategy

    Per "A Profitable Day Trading Strategy for The U.S. Equity Market"
    (Zarattini, Barbon, Aziz 2024 - Page 9):
    - Closes ALL positions at EOD regardless of P/L (converts stop to market order)
    - "If the stop loss was not reached intraday, we closed the position at the end of the trading session"
    """

    def execute(self, event):
        """
        Execute end-of-day position closure and generate daily report

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.info("Executing end-of-day position closure")

        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        # Get all remaining open positions
        open_positions = self.database_manager.get_open_positions()

        if not open_positions:
            logger.info("No open positions to close at EOD")
            self.state_manager.sendTelegramMessage("🕐 EOD: No open positions to close")
            return

        logger.info(f"Checking {len(open_positions)} positions for EOD closure (academic strategy: close ALL positions)")

        closed_positions = []
        left_open_positions = []

        # Close each position at EOD
        for position in open_positions:
            result = self._close_position_eod(position, now)
            if result == 'CLOSED':
                closed_positions.append(position)
            elif result == 'LEFT_OPEN':
                left_open_positions.append(position)

        # Send EOD closure notification
        self._send_eod_notification(closed_positions, left_open_positions)

    def _close_position_eod(self, position, now):
        """
        Close a single position at end of day (Academic Strategy)

        Closes ALL positions regardless of profitability per the academic paper's methodology.
        Paper (Page 9): "If the stop loss was not reached intraday, we closed the position
        at the end of the trading session (i.e., 4:00 pm ET)."

        Args:
            position: Position record (required)
            now: Current datetime (required)

        Returns:
            'CLOSED' if position was closed, 'LEFT_OPEN' if price unavailable, None if error

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if now is None:
            raise ValueError("now is REQUIRED")

        # Get current market price for EOD exit
        current_price = self.client.get_stock_price(position.symbol)
        if not current_price:
            logger.warning(f"Could not get current price for {position.symbol}, leaving position open")
            return 'LEFT_OPEN'

        # Academic ORB Strategy: Close ALL positions at EOD regardless of P/L
        # Paper (Page 9): "If the stop loss was not reached intraday, we closed the position
        # at the end of the trading session (i.e., 4:00 pm ET)."
        position_service = PositionService(self.application_context)
        unrealized_pnl = position_service.calculate_pnl(position, current_price)
        is_profitable = self._is_profitable(position, current_price)

        pnl_status = "PROFITABLE" if is_profitable else "UNPROFITABLE"
        logger.info(
            f"Position {position.id} ({position.symbol}) is {pnl_status} at ${current_price:.2f} "
            f"(entry: ${position.entry_price:.2f}, unrealized P&L: ${unrealized_pnl:.2f}) - closing at EOD"
        )

        # Convert stop order to market order for immediate execution
        success = self.client.convert_stop_to_market(position.stop_order_id)

        if success:
            # Update position exit reason in database for tracking
            self.database_manager.update_position_status(
                position.id,
                'OPEN',  # Status stays OPEN until ManageStockPositionsCommand detects fill
                exit_reason="EOD_EXIT"  # Track why we initiated the exit
            )

            # Update position object for temporary reporting (will be updated properly when filled)
            position.exit_reason = "EOD_EXIT"
            position.status = 'OPEN'  # Still open until fill detected

            logger.info(f"Stop order converted to market for EOD position {position.id}")
            return 'CLOSED'
        else:
            logger.error(f"Failed to convert stop order for EOD position {position.id}")
            return None

    def _is_profitable(self, position, current_price):
        """
        Check if a position is currently profitable

        Args:
            position: Position record (required)
            current_price: Current market price (required)

        Returns:
            Boolean indicating if position is profitable

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if current_price is None or current_price <= 0:
            raise ValueError(f"current_price must be positive, got: {current_price}")

        if position.direction == 'LONG':
            # LONG is profitable when current price > entry price
            return current_price > position.entry_price
        else:  # SHORT
            # SHORT is profitable when current price < entry price
            return current_price < position.entry_price

    def _send_eod_notification(self, closed_positions, left_open_positions):
        """
        Send notification about EOD position management (Academic Strategy)

        Args:
            closed_positions: List of positions successfully closed at EOD (required)
            left_open_positions: List of positions that failed to close (required)

        Raises:
            ValueError: If any parameter is None
        """
        if closed_positions is None:
            raise ValueError("closed_positions is REQUIRED")
        if left_open_positions is None:
            raise ValueError("left_open_positions is REQUIRED")

        logger.info(
            f"Sending EOD notification: {len(closed_positions)} closed at EOD, "
            f"{len(left_open_positions)} failed to close"
        )

        # Build notification message
        if not closed_positions and not left_open_positions:
            message = "🕐 EOD: No positions to manage"
        else:
            message = "🕐 **EOD CLOSURE (Academic Strategy)**\n\n"

            if closed_positions:
                message += f"✅ Closed {len(closed_positions)} position(s) at EOD:\n"
                for pos in closed_positions:
                    message += f"  • {pos.symbol} ({pos.direction})\n"
                message += "\n"

            if left_open_positions:
                message += f"⚠️ Failed to close {len(left_open_positions)} position(s):\n"
                for pos in left_open_positions:
                    message += f"  • {pos.symbol} ({pos.direction})\n"

        self.state_manager.sendTelegramMessage(message)
        logger.info(f"EOD notification sent")