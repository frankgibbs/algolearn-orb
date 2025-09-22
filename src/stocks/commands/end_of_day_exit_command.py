from src.core.command import Command
from src.core.constants import *
from src import logger
import pytz
from datetime import datetime
from prettytable import PrettyTable

class EndOfDayExitCommand(Command):
    """Handle end-of-day position closure and daily reporting"""

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

        logger.info(f"Closing {len(open_positions)} remaining positions at EOD")

        closed_positions = []

        # Close all remaining positions
        for position in open_positions:
            closed_position = self._close_position_eod(position, now)
            if closed_position:
                closed_positions.append(closed_position)

        # Send EOD closure notification
        self._send_eod_notification(closed_positions)

    def _close_position_eod(self, position, now):
        """
        Close a single position at end of day

        Args:
            position: Position record (required)
            now: Current datetime (required)

        Returns:
            Updated position record with exit details, or None if failed

        Raises:
            ValueError: If any parameter is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if now is None:
            raise ValueError("now is REQUIRED")

        logger.info(f"Converting stop order to market order for EOD closure {position.id} ({position.symbol})")

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
            return position
        else:
            logger.error(f"Failed to convert stop order for EOD position {position.id}")
            return None

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

    def _send_eod_notification(self, closed_positions):
        """
        Send notification about positions closed at EOD

        Args:
            closed_positions: List of positions closed at EOD (required)

        Raises:
            ValueError: If closed_positions is None
        """
        if closed_positions is None:
            raise ValueError("closed_positions is REQUIRED")

        if not closed_positions:
            self.state_manager.sendTelegramMessage("🕐 EOD: No positions were closed")
            return

        logger.info(f"Sending EOD notification for {len(closed_positions)} positions initiated for closure")

        # Create simple table with Symbol, Direction, Status
        table = PrettyTable()
        table.field_names = ["Symbol", "Direction", "Status"]
        table.align = "r"

        for pos in closed_positions:
            table.add_row([
                pos.symbol,
                pos.direction,
                "Closing..."
            ])

        # Send notification with table
        message = f"🕐 **EOD CLOSURES:** {len(closed_positions)} positions initiated for closure\n"
        message += f"Converting stop orders to market orders for immediate execution\n\n"
        message += f"```\n{table}\n```"

        self.state_manager.sendTelegramMessage(message)
        logger.info(f"EOD notification sent: {len(closed_positions)} positions initiated for closure")