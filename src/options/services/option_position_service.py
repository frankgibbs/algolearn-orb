"""
OptionPositionService - Position tracking and P&L updates for multi-leg spreads

Monitors open positions, calculates real-time P&L, and syncs with IB portfolio data.
"""

from src import logger
from datetime import datetime
from typing import List, Dict, Optional


class OptionPositionService:
    """Service for tracking and updating option positions"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.application_context = application_context
        self.client = application_context.client
        self.db_manager = application_context.option_db_manager

    def update_position_pnl(self, order_id: int) -> Dict:
        """
        Update position with current market prices and P&L

        Args:
            order_id: Position ID (required)

        Returns:
            Dict with updated position info

        Raises:
            ValueError: If order_id is invalid
            RuntimeError: If position not found or update fails
        """
        if not order_id:
            raise ValueError("order_id is REQUIRED")

        logger.debug(f"Updating P&L for position {order_id}")

        try:
            # Get position from database
            position = self.db_manager.get_position(order_id)
            if not position:
                raise RuntimeError(f"Position not found for order_id {order_id}")

            # Get current market prices for all legs
            current_value = 0.0
            for leg in position.legs:
                # Get option quote with Greeks (more reliable than get_option_quote)
                quote = self.client.get_option_greeks(
                    symbol=position.symbol,
                    expiry=leg.expiry,
                    strike=leg.strike,
                    right=leg.right
                )

                if quote:
                    # Calculate mid price from bid/ask, or use IB's mark price
                    if 'mid' in quote:
                        leg_price = quote['mid']
                    elif quote.get('bid') and quote.get('ask'):
                        leg_price = (quote['bid'] + quote['ask']) / 2
                    elif 'option_price' in quote:
                        leg_price = quote['option_price']  # IB's mark price
                    else:
                        logger.warning(f"No price data in quote for {position.symbol} {leg.strike}{leg.right}")
                        continue

                    # Calculate leg value (buy = cost, sell = credit)
                    if leg.action == "BUY":
                        current_value -= leg_price * leg.quantity  # Paid for this leg
                    else:  # SELL
                        current_value += leg_price * leg.quantity  # Received for this leg

            # Convert to dollars (100 shares per contract)
            current_value = current_value * 100

            # Calculate unrealized P&L
            # For credit spreads: P&L = credit received - current value (want value to go to zero)
            # For debit spreads: P&L = current value - debit paid (want value to increase)
            if position.is_credit_spread:
                unrealized_pnl = (position.net_credit * 100) - current_value
            else:
                unrealized_pnl = current_value - abs(position.net_credit * 100)

            # Update database
            self.db_manager.update_position_pnl(
                order_id=order_id,
                current_value=current_value / 100,  # Store as per-contract price
                unrealized_pnl=unrealized_pnl
            )

            logger.debug(f"Position {order_id} P&L updated: ${unrealized_pnl:.2f}")

            return {
                'order_id': order_id,
                'symbol': position.symbol,
                'strategy_type': position.strategy_type,
                'current_value': current_value / 100,
                'unrealized_pnl': unrealized_pnl,
                'pct_of_max_profit': (unrealized_pnl / position.max_profit * 100) if position.max_profit > 0 else 0,
                'actual_roi': (unrealized_pnl / position.max_risk * 100) if position.max_risk > 0 else 0,
                'dte': position.days_to_expiration
            }

        except Exception as e:
            logger.error(f"Error updating position P&L: {e}")
            raise RuntimeError(f"Failed to update position P&L: {str(e)}")

    def list_open_positions(self, symbol: str = None) -> List[Dict]:
        """
        List all open option positions with current P&L

        Args:
            symbol: Optional symbol filter

        Returns:
            List of dicts with position info including current P&L

        Raises:
            RuntimeError: If query fails
        """
        logger.info(f"Listing open positions{' for ' + symbol if symbol else ''}")

        try:
            # Get open positions from database
            positions = self.db_manager.get_open_positions(symbol=symbol)

            result = []
            for position in positions:
                # Update P&L for each position
                try:
                    pnl_info = self.update_position_pnl(position.id)

                    position_info = {
                        'order_id': position.id,
                        'symbol': position.symbol,
                        'strategy_type': position.strategy_type,
                        'status': position.status,
                        'entry_date': position.entry_date.isoformat() if position.entry_date else None,
                        'expiration_date': position.expiration_date.isoformat() if position.expiration_date else None,
                        'dte': position.days_to_expiration,
                        'net_credit': position.net_credit,
                        'max_risk': position.max_risk,
                        'max_profit': position.max_profit,
                        'entry_iv': position.entry_iv,
                        'current_value': pnl_info['current_value'],
                        'unrealized_pnl': pnl_info['unrealized_pnl'],
                        'pct_of_max_profit': pnl_info['pct_of_max_profit'],
                        'actual_roi': pnl_info['actual_roi'],
                        'profit_target_hit': position.profit_target_hit,
                        'needs_management': position.needs_management,
                        'legs': [
                            {
                                'action': leg.action,
                                'strike': leg.strike,
                                'right': leg.right,
                                'expiry': leg.expiry,
                                'quantity': leg.quantity
                            }
                            for leg in position.legs
                        ]
                    }

                    result.append(position_info)

                except Exception as e:
                    logger.warning(f"Error updating P&L for position {position.id}: {e}")
                    # Still include position but with stale data
                    position_info = {
                        'order_id': position.id,
                        'symbol': position.symbol,
                        'strategy_type': position.strategy_type,
                        'status': position.status,
                        'error': f"Could not update P&L: {str(e)}"
                    }
                    result.append(position_info)

            logger.info(f"Found {len(result)} open positions")
            return result

        except Exception as e:
            logger.error(f"Error listing open positions: {e}")
            raise RuntimeError(f"Failed to list open positions: {str(e)}")

    def get_all_positions(self, days_back: int = 30, symbol: str = None, status: str = None) -> List[Dict]:
        """
        Get all option positions within date range

        Args:
            days_back: Number of days back to query (default: 30)
            symbol: Optional symbol filter
            status: Optional status filter ("OPEN", "CLOSED", "PENDING", "CANCELLED")

        Returns:
            List of dicts with position info

        Raises:
            ValueError: If days_back is invalid
            RuntimeError: If query fails
        """
        if days_back is None or days_back < 0:
            raise ValueError("days_back must be >= 0")

        logger.info(f"Getting all positions from last {days_back} days")

        try:
            # Get positions from database
            positions = self.db_manager.get_all_positions(days_back=days_back, symbol=symbol)

            # Filter by status if specified
            if status:
                positions = [p for p in positions if p.status == status]

            result = []
            for position in positions:
                position_info = {
                    'order_id': position.id,
                    'symbol': position.symbol,
                    'strategy_type': position.strategy_type,
                    'status': position.status,
                    'entry_date': position.entry_date.isoformat() if position.entry_date else None,
                    'expiration_date': position.expiration_date.isoformat() if position.expiration_date else None,
                    'dte_at_entry': position.dte_at_entry,
                    'dte_remaining': position.days_to_expiration if position.status == "OPEN" else None,
                    'net_credit': position.net_credit,
                    'max_risk': position.max_risk,
                    'max_profit': position.max_profit,
                    'roi_target': position.roi_target,
                    'entry_iv': position.entry_iv,
                    'unrealized_pnl': position.unrealized_pnl if position.status == "OPEN" else None,
                    'realized_pnl': position.realized_pnl if position.status == "CLOSED" else None,
                    'exit_date': position.exit_date.isoformat() if position.exit_date else None,
                    'exit_reason': position.exit_reason,
                    'legs': [
                        {
                            'action': leg.action,
                            'strike': leg.strike,
                            'right': leg.right,
                            'expiry': leg.expiry,
                            'quantity': leg.quantity,
                            'fill_price': leg.fill_price
                        }
                        for leg in position.legs
                    ]
                }

                result.append(position_info)

            logger.info(f"Found {len(result)} positions")
            return result

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            raise RuntimeError(f"Failed to get positions: {str(e)}")
