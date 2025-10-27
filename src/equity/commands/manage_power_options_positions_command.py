"""
ManagePowerOptionsPositionsCommand - Monitor PowerOptions position lifecycles

Monitors both equity holdings AND option positions for PowerOptions strategy:
- PENDING equity purchases → OPEN (stock filled)
- PENDING option orders → OPEN (option filled)
- OPEN options with closing orders → CLOSED (update equity premium)
- OPEN options expired → CLOSED (mark expired, update equity premium)
- Detect assignments (equity shares decrease)

Follows same pattern as ManageOptionPositionsCommand and ManageStockPositionsCommand.
"""

from src.core.command import Command
from src.core.constants import *
from src import logger
import pytz
import time
from datetime import datetime


class ManagePowerOptionsPositionsCommand(Command):
    """Monitor PowerOptions strategy: equity holdings + covered calls/ratio spreads"""

    def execute(self, event):
        """
        Execute position monitoring for both equity and options

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.debug("Checking PowerOptions position state transitions")

        # Validate market hours
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        if not self._is_market_hours(now):
            return

        # 1. Check pending stock purchases (PENDING → OPEN)
        self._check_pending_equity_purchases()

        # 2. Check pending option orders (PENDING → OPEN)
        self._check_pending_option_positions()

        # 3. Check closing option orders (OPEN → CLOSED, update equity premium)
        self._check_closing_option_positions()

        # 4. Check for expired options (OPEN → CLOSED via IB position query)
        self._check_expired_options()

        # 5. Check for option assignments (equity shares decreased)
        self._check_option_assignments()

    def _check_pending_equity_purchases(self):
        """Check PENDING equity holdings for stock fills → transition to OPEN"""
        equity_db_manager = self.application_context.equity_db_manager
        pending_holdings = equity_db_manager.get_pending_holdings()

        if not pending_holdings:
            logger.debug("No pending equity purchases to check")
            return

        logger.info(f"Checking {len(pending_holdings)} pending equity purchases")

        for holding in pending_holdings:
            self._check_equity_purchase_fill(holding)
            # Small delay to avoid overwhelming IB
            time.sleep(0.1)

    def _check_equity_purchase_fill(self, holding):
        """
        Check if equity purchase order has been filled

        Args:
            holding: EquityHolding record with status='PENDING' (required)

        Raises:
            ValueError: If holding is None
        """
        if holding is None:
            raise ValueError("holding is REQUIRED")

        logger.debug(f"Checking stock order {holding.purchase_order_id} for {holding.symbol}")

        # Check for fills
        fill_info = self.client.get_fills_by_order_id(holding.purchase_order_id, timeout=5)

        if fill_info:
            # Extract fill price
            avg_fill_price = fill_info.get('lmtPrice')
            if avg_fill_price is None or avg_fill_price == 0:
                logger.error(f"Stock order {holding.purchase_order_id} filled but has no valid fill price")
                logger.error(f"Fill info: {fill_info}")
                self.state_manager.sendTelegramMessage(
                    f"Stock order {holding.purchase_order_id} ({holding.symbol}) filled but has no valid fill price"
                )
                raise RuntimeError(f"Stock order {holding.purchase_order_id} filled with invalid price: {avg_fill_price}")

            fill_time = datetime.now()

            logger.info(f"Equity holding {holding.id} ({holding.symbol}) filled at ${avg_fill_price}")

            # Transition to OPEN
            self._transition_equity_to_open(holding, avg_fill_price, fill_time)

    def _transition_equity_to_open(self, holding, fill_price, fill_time):
        """
        Transition equity holding from PENDING to OPEN

        Args:
            holding: EquityHolding record (required)
            fill_price: Fill price per share from IB (required)
            fill_time: Fill time (required)

        Raises:
            ValueError: If any parameter is None
        """
        if holding is None:
            raise ValueError("holding is REQUIRED")
        if fill_price is None:
            raise ValueError("fill_price is REQUIRED")

        logger.info(f"Equity holding {holding.id} ({holding.symbol}) filled at ${fill_price}")

        # Update to OPEN status (actual_cost_basis might differ from original estimate)
        equity_db_manager = self.application_context.equity_db_manager
        equity_db_manager.update_holding_status(
            holding.id,
            'OPEN',
            original_cost_basis=fill_price  # Update with actual fill price
        )

        # Send notification
        self.state_manager.sendTelegramMessage(
            f"✅ Stock Purchase FILLED\n"
            f"Symbol: {holding.symbol}\n"
            f"Shares: {holding.total_shares}\n"
            f"Fill Price: ${fill_price:.2f}\n"
            f"Total Cost: ${fill_price * holding.total_shares:.2f}\n"
            f"Order ID: {holding.purchase_order_id}"
        )

    def _check_pending_option_positions(self):
        """Check PENDING option positions → transition to OPEN"""
        option_db_manager = self.application_context.option_db_manager
        pending_options = option_db_manager.get_all_positions(days_back=7)
        pending_options = [p for p in pending_options if p.status == "PENDING"]

        if not pending_options:
            logger.debug("No pending option positions to check")
            return

        logger.info(f"Checking {len(pending_options)} pending option positions")

        for position in pending_options:
            self._check_option_position_fill(position)
            # Small delay to avoid overwhelming IB
            time.sleep(0.1)

    def _check_option_position_fill(self, position):
        """
        Check if option combo order has been filled

        Args:
            position: OptionPosition record with status='PENDING' (required)

        Raises:
            ValueError: If position is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")

        logger.debug(f"Checking combo order {position.id} for {position.symbol} {position.strategy_type}")

        # Check for fills
        fill_info = self.client.get_fills_by_order_id(position.id, timeout=5)

        if fill_info:
            # For combo orders, use the net credit/debit from position record
            fill_price = position.net_credit

            if fill_price is None or fill_price == 0:
                raise RuntimeError(
                    f"Combo order {position.id} filled but position.net_credit is invalid: {fill_price}"
                )

            fill_time = datetime.now()

            logger.info(f"Option position {position.id} ({position.symbol} {position.strategy_type}) filled at ${fill_price}")

            # Transition to OPEN
            self._transition_option_to_open(position, fill_price, fill_time)

    def _transition_option_to_open(self, position, fill_price, fill_time):
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

        # Add equity link info if this is a covered position
        if position.equity_holding_id:
            equity_db_manager = self.application_context.equity_db_manager
            equity_holding = equity_db_manager.get_holding_by_id(position.equity_holding_id)
            if equity_holding:
                message += f"\nLinked to equity holding: {equity_holding.symbol} ({equity_holding.total_shares} shares)"

        self.state_manager.sendTelegramMessage(message)
        logger.info(f"Fill notification sent for option position {position.id}")

    def _check_closing_option_positions(self):
        """Check OPEN options with closing orders → CLOSED + update equity premium"""
        option_db_manager = self.application_context.option_db_manager
        open_positions = option_db_manager.get_open_positions()
        closing_positions = [p for p in open_positions if p.closing_order_id != 0]

        if not closing_positions:
            logger.debug("No closing orders to check")
            return

        logger.info(f"Checking {len(closing_positions)} closing orders")

        for position in closing_positions:
            self._check_closing_order_fill(position)
            # Small delay to avoid overwhelming IB
            time.sleep(0.1)

    def _check_closing_order_fill(self, position):
        """
        Check if closing order has been filled

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
            # Extract exit value
            exit_value = fill_info.get('lmtPrice')
            if exit_value is None:
                raise RuntimeError(
                    f"Closing order {position.closing_order_id} filled but lmtPrice is None"
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
            self._transition_option_to_closed(position, exit_value, realized_pnl, fill_time)

            # Update linked equity holding premium
            if position.equity_holding_id:
                self._update_equity_premium(position, exit_value)

    def _transition_option_to_closed(self, position, exit_value, realized_pnl, fill_time):
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
            exit_reason=position.exit_reason or "MANUAL_CLOSE",
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
            f"Exit Reason: {position.exit_reason or 'MANUAL_CLOSE'}\n"
            f"Position ID: {position.id}"
        )

        self.state_manager.sendTelegramMessage(message)
        logger.info(f"Close notification sent for option position {position.id}")

    def _update_equity_premium(self, option_position, exit_value):
        """
        Update equity holding premium when option closes (basis reduction)

        Args:
            option_position: OptionPosition record (required)
            exit_value: Closing price from IB (required)

        Raises:
            ValueError: If any parameter is None
        """
        if option_position is None:
            raise ValueError("option_position is REQUIRED")
        if exit_value is None:
            raise ValueError("exit_value is REQUIRED")

        equity_db_manager = self.application_context.equity_db_manager
        equity_holding = equity_db_manager.get_holding_by_id(option_position.equity_holding_id)

        if not equity_holding:
            logger.warning(
                f"Option {option_position.id} references missing equity holding {option_position.equity_holding_id}"
            )
            return

        # NOTE: Premium tracking removed - calculated on-demand via EquityService
        # The realized_pnl in option_position is sufficient for cost basis calculation
        logger.info(
            f"Option position {option_position.id} closed for {equity_holding.symbol} - "
            f"premium will be included in next cost basis calculation"
        )

    def _check_expired_options(self):
        """Check for expired options by comparing expiration date to current time"""
        # Query all OPEN option positions
        option_db_manager = self.application_context.option_db_manager
        open_positions = option_db_manager.get_open_positions()

        # Filter: only those without closing orders (closing_order_id == 0)
        open_no_closing = [p for p in open_positions if p.closing_order_id == 0]

        if not open_no_closing:
            logger.debug("No open options without closing orders to check for expiration")
            return

        logger.debug(f"Checking {len(open_no_closing)} open options for expiration by date")

        # Get current time for comparison
        now = datetime.now()

        # Check each open position - if past expiration date, it expired
        for position in open_no_closing:
            if position.expiration_date and position.expiration_date < now:
                logger.info(
                    f"Option position {position.id} ({position.symbol} {position.strategy_type}) "
                    f"expired on {position.expiration_date.strftime('%Y-%m-%d')} - marking as EXPIRED_WORTHLESS"
                )
                self._mark_option_expired(position)

    def _mark_option_expired(self, position):
        """
        Mark option as expired worthless and update equity premium

        Args:
            position: OptionPosition record (required)

        Raises:
            ValueError: If position is None
        """
        if position is None:
            raise ValueError("position is REQUIRED")

        logger.info(f"Marking option position {position.id} as EXPIRED_WORTHLESS")

        # For credit spreads, we keep the full premium (expires worthless = max profit)
        # For debit spreads, we lose the full debit (expires worthless = max loss)
        if position.is_credit_spread:
            realized_pnl = position.net_credit * 100  # Full premium kept
            exit_value = 0.0  # Position worth zero
        else:
            realized_pnl = -abs(position.net_credit) * 100  # Full debit lost
            exit_value = 0.0

        # Close position with EXPIRED_WORTHLESS reason
        option_db_manager = self.application_context.option_db_manager
        option_db_manager.close_position(
            order_id=position.id,
            exit_value=exit_value,
            exit_reason="EXPIRED_WORTHLESS",
            realized_pnl=realized_pnl
        )

        # NOTE: Premium tracking removed - calculated on-demand via EquityService
        # The realized_pnl in option_position is sufficient for cost basis calculation
        if position.equity_holding_id:
            equity_db_manager = self.application_context.equity_db_manager
            equity_holding = equity_db_manager.get_holding_by_id(position.equity_holding_id)

            if equity_holding:
                logger.info(
                    f"Option position {position.id} expired for {equity_holding.symbol} - "
                    f"realized P&L ${realized_pnl:.2f} will be included in next cost basis calculation"
                )

        # Send notification
        pnl_emoji = "✅" if realized_pnl > 0 else "❌"
        self.state_manager.sendTelegramMessage(
            f"{pnl_emoji} Option Position EXPIRED\n"
            f"Symbol: {position.symbol}\n"
            f"Strategy: {position.strategy_type}\n"
            f"Realized P&L: ${realized_pnl:.2f}\n"
            f"Position ID: {position.id}"
        )

    def _check_option_assignments(self):
        """Check for option assignments by detecting equity share decreases"""
        # Query all OPEN equity holdings
        equity_db_manager = self.application_context.equity_db_manager
        open_holdings = equity_db_manager.get_open_holdings()

        if not open_holdings:
            logger.debug("No open equity holdings to check for assignments")
            return

        logger.debug(f"Checking {len(open_holdings)} open equity holdings for assignments")

        # Query IB for current equity positions
        # Let exceptions propagate - CommandInvoker will handle them
        ib_equity_positions = self.client.get_portfolio_positions()
        ib_positions_by_symbol = {pos.get('symbol'): pos for pos in ib_equity_positions}

        # Check each holding - if shares decreased, assignment occurred
        for holding in open_holdings:
            ib_position = ib_positions_by_symbol.get(holding.symbol)

            if ib_position:
                ib_shares = int(ib_position.get('quantity', 0))

                if ib_shares < holding.total_shares:
                    shares_assigned = holding.total_shares - ib_shares
                    logger.info(
                        f"Assignment detected: {holding.symbol} shares {holding.total_shares} → {ib_shares} "
                        f"({shares_assigned} shares assigned)"
                    )
                    self._handle_assignment(holding, ib_shares, shares_assigned)
            else:
                # Position completely missing from IB - fully assigned
                logger.info(
                    f"Full assignment detected: {holding.symbol} {holding.total_shares} shares "
                    f"(position missing from IB)"
                )
                self._handle_assignment(holding, 0, holding.total_shares)

    def _handle_assignment(self, holding, new_shares, shares_assigned):
        """
        Handle option assignment (shares sold)

        Args:
            holding: EquityHolding record (required)
            new_shares: New total share count after assignment (required)
            shares_assigned: Number of shares assigned (required)

        Raises:
            ValueError: If any parameter is None
        """
        if holding is None:
            raise ValueError("holding is REQUIRED")
        if new_shares is None or new_shares < 0:
            raise ValueError("new_shares is REQUIRED and must be >= 0")
        if shares_assigned is None or shares_assigned <= 0:
            raise ValueError("shares_assigned is REQUIRED and must be positive")

        equity_db_manager = self.application_context.equity_db_manager

        if new_shares == 0:
            # Full assignment - close the equity holding
            # Get assignment price from the option position that was assigned
            assignment_price = self._get_assignment_strike_price(holding)
            realized_pnl = (assignment_price - holding.effective_cost_basis) * shares_assigned

            equity_db_manager.close_holding(
                holding_id=holding.id,
                exit_price=assignment_price,
                exit_reason="ASSIGNED",
                realized_pnl=realized_pnl
            )

            logger.info(
                f"Equity holding {holding.id} ({holding.symbol}) fully assigned and closed: "
                f"{shares_assigned} shares @ ${assignment_price:.2f}"
            )

            # Send notification
            self.state_manager.sendTelegramMessage(
                f"📤 FULL ASSIGNMENT\n"
                f"Symbol: {holding.symbol}\n"
                f"Shares Assigned: {shares_assigned}\n"
                f"Assignment Price: ${assignment_price:.2f}\n"
                f"Stock P&L: ${realized_pnl:.2f}\n"
                f"Equity holding CLOSED"
            )
        else:
            # Partial assignment - update share count
            equity_db_manager.update_shares(
                holding_id=holding.id,
                new_total_shares=new_shares
            )

            logger.info(
                f"Equity holding {holding.id} ({holding.symbol}) partially assigned: "
                f"{shares_assigned} shares assigned, {new_shares} remaining"
            )

            # Send notification
            self.state_manager.sendTelegramMessage(
                f"📤 PARTIAL ASSIGNMENT\n"
                f"Symbol: {holding.symbol}\n"
                f"Shares Assigned: {shares_assigned}\n"
                f"Remaining Shares: {new_shares}"
            )

    def _get_assignment_strike_price(self, holding):
        """
        Get the strike price of the assigned option position

        For covered calls/ratio spreads, the assignment price is the strike price
        of the short call leg, not the original stock purchase price.

        Args:
            holding: EquityHolding record (required)

        Returns:
            Strike price from most recent option position linked to this holding

        Raises:
            ValueError: If holding is None
            RuntimeError: If no option position found or strike cannot be determined
        """
        if holding is None:
            raise ValueError("holding is REQUIRED")

        option_db_manager = self.application_context.option_db_manager

        # Query all option positions for this equity holding
        # Using get_all_positions with a wide lookback to ensure we find the assigned option
        all_positions = option_db_manager.get_all_positions(days_back=90, symbol=holding.symbol)

        # Filter for positions linked to this equity holding
        linked_positions = [p for p in all_positions if p.equity_holding_id == holding.id]

        if not linked_positions:
            logger.warning(
                f"No option positions found for equity holding {holding.id} ({holding.symbol}). "
                f"Using original cost basis ${holding.original_cost_basis:.2f} as fallback."
            )
            return holding.original_cost_basis

        # Get the most recent option position (likely the one that got assigned)
        # Sort by entry_date descending
        linked_positions.sort(key=lambda p: p.entry_date, reverse=True)
        most_recent_option = linked_positions[0]

        logger.info(
            f"Found option position {most_recent_option.id} ({most_recent_option.strategy_type}) "
            f"for equity holding {holding.id}"
        )

        # Extract strike price from the SHORT call leg
        # For covered calls/ratio spreads, we sold calls, so find SELL + C legs
        short_call_legs = [
            leg for leg in most_recent_option.legs
            if leg.action == 'SELL' and leg.right == 'C'
        ]

        if not short_call_legs:
            logger.error(
                f"No short call legs found in option position {most_recent_option.id}. "
                f"Legs: {most_recent_option.legs}"
            )
            raise RuntimeError(
                f"Cannot determine assignment strike: no short call legs in position {most_recent_option.id}"
            )

        # Use the highest strike if multiple short calls (for ratio spreads)
        # Assignment happens at the short strike
        strike_price = max(leg.strike for leg in short_call_legs)

        logger.info(
            f"Assignment strike price for {holding.symbol}: ${strike_price:.2f} "
            f"(from option position {most_recent_option.id})"
        )

        return strike_price

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

        # Same as ORB strategy: 6:30 AM - 1:00 PM PST
        hour = now.hour
        minute = now.minute

        if hour < 6 or (hour == 6 and minute < 30) or hour >= 13:
            return False

        # Check weekday
        return now.weekday() < 5
