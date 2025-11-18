from src.core.command import Command
from src.core.constants import *
from src import logger
from prettytable import PrettyTable
from datetime import date
import pytz
from datetime import datetime
from sqlalchemy import func


class DailyPnlReportCommand(Command):
    """
    Generate and send daily PNL report at 12:55 PM PST

    Shows all closed positions for the day with Symbol and P&L columns,
    plus a total row and summary statistics.
    """

    def execute(self, event):
        """
        Execute daily PNL report generation

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.info("Generating daily PNL report")

        pacific_tz = pytz.timezone('US/Pacific')
        today = datetime.now(pacific_tz).date()

        # Query positions CLOSED today (filter by exit_time, not created_at)
        # This fixes the bug where get_all_positions() was filtering by created_at
        from src.stocks.models.position import Position
        session = self.database_manager.get_session()
        try:
            closed_positions = session.query(Position).filter(
                func.date(Position.exit_time) == today,
                Position.status == 'CLOSED'
            ).all()
        finally:
            session.close()

        if not closed_positions:
            logger.info("No closed positions for today")
            self.state_manager.sendTelegramMessage(
                f"📊 DAILY PNL REPORT - {today.strftime('%Y-%m-%d')}\n\n"
                "No positions closed today."
            )
            return

        # Generate report
        report = self._generate_pnl_report(closed_positions, today)

        # Send via Telegram
        self.state_manager.sendTelegramMessage(report)
        logger.info(f"Daily PNL report sent for {len(closed_positions)} closed positions")

    def _generate_pnl_report(self, closed_positions, report_date):
        """
        Generate formatted PNL report with prettytable

        Args:
            closed_positions: List of closed Position records (required)
            report_date: Date for the report (required)

        Returns:
            str: Formatted report message

        Raises:
            ValueError: If any parameter is None
        """
        if closed_positions is None:
            raise ValueError("closed_positions is REQUIRED")
        if report_date is None:
            raise ValueError("report_date is REQUIRED")

        # Create table with Symbol and P&L columns
        table = PrettyTable(['Symbol', 'P&L'])
        table.align['Symbol'] = 'l'
        table.align['P&L'] = 'r'

        # Calculate statistics
        total_pnl = 0.0
        winners = 0
        losers = 0

        # Add each position to table
        for position in closed_positions:
            pnl = position.realized_pnl if position.realized_pnl is not None else 0.0
            total_pnl += pnl

            # Track winners/losers
            if pnl > 0:
                winners += 1
            elif pnl < 0:
                losers += 1

            # Format P&L with +/- prefix and $ sign
            if pnl >= 0:
                pnl_str = f"+${pnl:.2f}"
            else:
                pnl_str = f"-${abs(pnl):.2f}"

            table.add_row([position.symbol, pnl_str])

        # Add total row
        if total_pnl >= 0:
            total_str = f"+${total_pnl:.2f}"
        else:
            total_str = f"-${abs(total_pnl):.2f}"

        table.add_row(['TOTAL', total_str])

        # Build final message - just the table, no header or footer
        message = f"<pre>{table}</pre>"

        return message
