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

    # NOTE: update_position_pnl() removed
    # Unrealized P&L should be calculated on-demand using get_option_quote MCP tool
    # Do not store derived/calculated values that change constantly

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
                    # NOTE: unrealized_pnl removed - calculate on-demand using get_option_quote MCP tool
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
