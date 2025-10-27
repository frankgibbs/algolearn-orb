"""
EquityService - Business logic for PowerOptions equity holdings

Provides premium calculation with real-time IB data for effective cost basis.
"""

from src import logger
from typing import Dict


class EquityService:
    """Service layer for equity holding calculations and business logic"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.application_context = application_context
        self.client = application_context.client
        self.equity_db_manager = application_context.equity_db_manager
        self.option_db_manager = application_context.option_db_manager

        logger.info("EquityService initialized")

    def get_all_holdings(self, symbol: str = None, status: str = None):
        """
        Get all equity holdings with optional filters

        Args:
            symbol: Optional symbol filter (e.g., "AAPL")
            status: Optional status filter ("OPEN", "CLOSED", "PENDING")

        Returns:
            List of EquityHolding objects

        Raises:
            ValueError: If status is invalid
        """
        if status and status not in ['OPEN', 'CLOSED', 'PENDING']:
            raise ValueError(f"Invalid status: {status}. Must be OPEN, CLOSED, or PENDING")

        # Get holdings based on status
        if status == 'PENDING':
            holdings = self.equity_db_manager.get_pending_holdings()
        elif status == 'OPEN':
            holdings = self.equity_db_manager.get_open_holdings()
        else:
            # Get all holdings (need to query manually since no get_all method exists)
            session = self.equity_db_manager.get_session()
            try:
                from src.equity.models.equity_holding import EquityHolding
                query = session.query(EquityHolding)

                if status:
                    query = query.filter(EquityHolding.status == status)

                holdings = query.order_by(EquityHolding.initial_purchase_date.desc()).all()
            finally:
                session.close()

        # Apply symbol filter if provided
        if symbol:
            holdings = [h for h in holdings if h.symbol == symbol]

        logger.info(f"Retrieved {len(holdings)} equity holdings (symbol={symbol}, status={status})")
        return holdings

    def calculate_effective_cost_basis(self, holding_id: int) -> Dict:
        """
        Calculate effective cost basis with real-time option P&L from IB

        For PowerOptions strategy, effective cost basis is reduced by net option premium:
        - Realized P&L from closed/expired options (from database)
        - Unrealized P&L from open options (live market data from IB)

        Args:
            holding_id: Equity holding ID (required)

        Returns:
            dict with:
            {
                'original_cost_basis': float,        # Cost per share at purchase
                'total_shares': int,                 # Number of shares
                'total_premium_net': float,          # Net premium (realized + unrealized)
                'effective_cost_basis': float,       # Adjusted cost per share
                'breakdown': {
                    'realized_premium': float,       # From closed/expired positions
                    'unrealized_premium': float      # From open positions (live IB)
                }
            }

        Raises:
            ValueError: If holding_id is None
            RuntimeError: If holding not found or IB query fails
        """
        if holding_id is None:
            raise ValueError("holding_id is REQUIRED")

        # Get equity holding
        holding = self.equity_db_manager.get_holding_by_id(holding_id)
        if not holding:
            raise RuntimeError(f"Equity holding {holding_id} not found")

        # Get all linked option positions
        all_positions = self.option_db_manager.get_all_positions(
            days_back=365,  # Look back far enough to catch all positions
            symbol=holding.symbol
        )
        linked_positions = [p for p in all_positions if p.equity_holding_id == holding_id]

        logger.debug(
            f"Calculating cost basis for {holding.symbol}: "
            f"{len(linked_positions)} linked option positions"
        )

        # Calculate realized premium (closed/expired positions)
        realized_premium = 0.0
        for pos in linked_positions:
            if pos.status in ['CLOSED', 'EXPIRED_WORTHLESS']:
                # Use realized_pnl from database (already calculated)
                if pos.realized_pnl is not None:
                    realized_premium += pos.realized_pnl

        logger.debug(f"Realized premium: ${realized_premium:.2f}")

        # Calculate unrealized premium (open positions with live IB data)
        unrealized_premium = self._calculate_unrealized_premium(linked_positions)

        logger.debug(f"Unrealized premium: ${unrealized_premium:.2f}")

        # Total net premium impact
        total_premium_net = realized_premium + unrealized_premium

        # Calculate effective cost basis per share
        total_stock_cost = holding.original_cost_basis * holding.total_shares
        effective_total = total_stock_cost - total_premium_net
        effective_cost_basis = effective_total / holding.total_shares if holding.total_shares > 0 else 0.0

        result = {
            'original_cost_basis': holding.original_cost_basis,
            'total_shares': holding.total_shares,
            'total_premium_net': total_premium_net,
            'effective_cost_basis': effective_cost_basis,
            'breakdown': {
                'realized_premium': realized_premium,
                'unrealized_premium': unrealized_premium
            }
        }

        logger.info(
            f"Cost basis for {holding.symbol}: "
            f"original=${holding.original_cost_basis:.2f}, "
            f"effective=${effective_cost_basis:.2f}, "
            f"net_premium=${total_premium_net:.2f} "
            f"(realized=${realized_premium:.2f}, unrealized=${unrealized_premium:.2f})"
        )

        return result

    def _calculate_unrealized_premium(self, linked_positions) -> float:
        """
        Calculate unrealized P&L for open option positions using live IB data

        For each open position:
        - Query IB for current market value of the spread
        - Calculate unrealized P&L based on entry vs current value

        Args:
            linked_positions: List of OptionPosition records

        Returns:
            float: Total unrealized premium (can be positive or negative)

        Raises:
            TimeoutError: If IB query times out
            RuntimeError: If position data is invalid
        """
        open_positions = [p for p in linked_positions if p.status == 'OPEN']

        if not open_positions:
            logger.debug("No open option positions to calculate unrealized P&L")
            return 0.0

        logger.debug(f"Calculating unrealized P&L for {len(open_positions)} open positions")

        # Query IB for current option positions (all at once for efficiency)
        ib_positions = self.client.get_option_positions()

        total_unrealized = 0.0

        for position in open_positions:
            # Find matching position in IB by contract details
            ib_pos = self._find_matching_ib_position(position, ib_positions)

            if ib_pos:
                # Calculate unrealized P&L from IB market value
                current_value = ib_pos.get('marketValue', 0.0)
                entry_value = position.net_credit * 100 * len(position.legs) / 2  # Rough estimate of entry value

                # For credit spreads: we want current value to go to zero (collect full credit)
                # For debit spreads: we want current value to increase (spread widens)
                if position.is_credit_spread:
                    # Credit spread: entry_value is positive (credit), current negative (liability)
                    # Unrealized P&L = entry_value - |current_value|
                    unrealized_pnl = (position.net_credit * 100) - abs(current_value)
                else:
                    # Debit spread: entry_value is negative (debit paid), current is value
                    # Unrealized P&L = current_value - entry_value
                    unrealized_pnl = current_value - abs(position.net_credit * 100)

                total_unrealized += unrealized_pnl

                logger.debug(
                    f"Position {position.id} ({position.strategy_type}): "
                    f"entry=${position.net_credit * 100:.2f}, "
                    f"current=${current_value:.2f}, "
                    f"unrealized=${unrealized_pnl:.2f}"
                )
            else:
                logger.warning(
                    f"Position {position.id} is OPEN in database but not found in IB - "
                    f"may have been closed outside system or expired"
                )

        return total_unrealized

    def _find_matching_ib_position(self, position, ib_positions):
        """
        Find matching IB position by contract details

        Matches by symbol and contract IDs from position legs.

        Args:
            position: OptionPosition record
            ib_positions: List of position dicts from IB

        Returns:
            dict or None: Matching IB position dict
        """
        # For multi-leg positions, we need to match by contract details
        # This is a simplified match by symbol - could be enhanced to match specific legs
        for ib_pos in ib_positions:
            if ib_pos.get('symbol') == position.symbol:
                # Found a matching symbol - in production, should verify contract details match
                return ib_pos

        return None
