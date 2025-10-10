"""
OptionOrderService - Order management for multi-leg option spreads

Handles placing, tracking, and canceling multi-leg option orders.
Integrates IBClient combo orders with OptionDatabaseManager.
"""

from src import logger
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class OptionOrderService:
    """Service for managing option orders"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.application_context = application_context
        self.client = application_context.client
        self.db_manager = application_context.option_db_manager

    def place_spread(
        self,
        symbol: str,
        strategy_type: str,
        legs: List[Dict],
        limit_price: float,
        expiration_date: datetime,
        entry_iv: float,
        time_in_force: str = "DAY"
    ) -> Dict:
        """
        Place a multi-leg spread order

        Args:
            symbol: Stock symbol (required)
            strategy_type: Strategy name like "BULL_PUT_SPREAD" (required)
            legs: List of leg dicts with action, strike, right, expiry, quantity (required)
            limit_price: Net credit (positive) or debit (negative) for spread (required)
            expiration_date: Option expiration datetime (required)
            entry_iv: Implied volatility at entry (required)
            time_in_force: "DAY" or "GTC" (default: "DAY")

        Returns:
            Dict with keys: order_id, status, message, position

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If order placement fails
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if not strategy_type:
            raise ValueError("strategy_type is REQUIRED")
        if not legs or len(legs) < 2:
            raise ValueError("legs is REQUIRED and must have at least 2 legs")
        if limit_price is None:
            raise ValueError("limit_price is REQUIRED")
        if not expiration_date:
            raise ValueError("expiration_date is REQUIRED")
        if entry_iv is None or entry_iv <= 0:
            raise ValueError("entry_iv is REQUIRED and must be > 0")

        logger.info(f"Placing {strategy_type} on {symbol}: {len(legs)} legs @ ${limit_price:.2f}")

        # Calculate max risk and max profit based on strategy
        max_risk, max_profit = self._calculate_risk_reward(legs, limit_price, strategy_type)

        # Calculate days to expiration
        dte_at_entry = (expiration_date - datetime.now()).days

        # Calculate ROI
        roi_target = (max_profit / max_risk * 100) if max_risk > 0 else 0

        try:
            # Place the combo order with IB
            order_result = self.client.place_combo_order(
                symbol=symbol,
                legs=legs,
                limit_price=limit_price,
                action="BUY",  # Always BUY the combo (individual legs have their own actions)
                time_in_force=time_in_force
            )

            if not order_result:
                raise RuntimeError("IB order submission returned no result")

            order_id = order_result.get('orderId')
            if not order_id:
                raise RuntimeError("No order ID returned from IB")

            # Save position to database
            position = self.db_manager.save_position(
                order_id=order_id,
                symbol=symbol,
                strategy_type=strategy_type,
                entry_date=datetime.now(),
                expiration_date=expiration_date,
                dte_at_entry=dte_at_entry,
                net_credit=limit_price,
                max_risk=max_risk,
                max_profit=max_profit,
                roi_target=roi_target,
                entry_iv=entry_iv,
                legs=legs
            )

            logger.info(f"Order placed successfully: {order_id} {symbol} {strategy_type}")

            return {
                'order_id': order_id,
                'status': 'PENDING',
                'message': f"Order {order_id} placed for {strategy_type} on {symbol}",
                'position': position,
                'max_risk': max_risk,
                'max_profit': max_profit,
                'roi_target': roi_target
            }

        except Exception as e:
            logger.error(f"Error placing spread order: {e}")
            raise RuntimeError(f"Failed to place spread order: {str(e)}")

    def cancel_order(self, order_id: int) -> Dict:
        """
        Cancel a pending option order

        Args:
            order_id: Order ID to cancel (required)

        Returns:
            Dict with keys: order_id, status, message

        Raises:
            ValueError: If order_id is invalid
            RuntimeError: If cancel fails
        """
        if not order_id:
            raise ValueError("order_id is REQUIRED")

        logger.info(f"Canceling order {order_id}")

        try:
            # Cancel the order with IB
            self.client.cancel_stock_order(order_id)

            # Update position status in database
            self.db_manager.update_position_status(order_id, "CANCELLED")

            logger.info(f"Order {order_id} cancelled successfully")

            return {
                'order_id': order_id,
                'status': 'CANCELLED',
                'message': f"Order {order_id} cancelled"
            }

        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            raise RuntimeError(f"Failed to cancel order: {str(e)}")

    def list_working_orders(self, symbol: str = None) -> List[Dict]:
        """
        List all pending/working option orders

        Args:
            symbol: Optional symbol filter

        Returns:
            List of dicts with order info: order_id, symbol, strategy_type, status, limit_price, etc.

        Raises:
            RuntimeError: If query fails
        """
        logger.info(f"Listing working orders{' for ' + symbol if symbol else ''}")

        try:
            # Get open orders from IB
            ib_orders = self.client.get_open_orders()

            # Get pending positions from database
            pending_positions = self.db_manager.get_all_positions(days_back=7, symbol=symbol)
            pending_positions = [p for p in pending_positions if p.status == "PENDING"]

            # Enrich with current market data
            working_orders = []
            for position in pending_positions:
                order_info = {
                    'order_id': position.id,
                    'symbol': position.symbol,
                    'strategy_type': position.strategy_type,
                    'status': position.status,
                    'limit_price': position.net_credit,
                    'max_risk': position.max_risk,
                    'max_profit': position.max_profit,
                    'roi_target': position.roi_target,
                    'dte': position.days_to_expiration,
                    'entry_date': position.entry_date.isoformat() if position.entry_date else None,
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

                # Add IB order status if available
                if position.id in ib_orders:
                    ib_order = ib_orders[position.id]
                    order_info['ib_status'] = ib_order.get('orderState')

                working_orders.append(order_info)

            logger.info(f"Found {len(working_orders)} working orders")
            return working_orders

        except Exception as e:
            logger.error(f"Error listing working orders: {e}")
            raise RuntimeError(f"Failed to list working orders: {str(e)}")

    def _calculate_risk_reward(self, legs: List[Dict], limit_price: float, strategy_type: str) -> tuple:
        """
        Calculate max risk and max profit for a spread

        Args:
            legs: List of leg dicts
            limit_price: Net credit/debit
            strategy_type: Strategy name

        Returns:
            Tuple of (max_risk, max_profit)
        """
        # For vertical spreads (2 legs)
        if len(legs) == 2:
            # Find the width of the spread
            strikes = sorted([leg['strike'] for leg in legs])
            spread_width = (strikes[1] - strikes[0]) * 100  # Convert to dollars (100 shares per contract)

            if limit_price > 0:  # Credit spread
                max_profit = limit_price * 100
                max_risk = spread_width - max_profit
            else:  # Debit spread
                max_risk = abs(limit_price) * 100
                max_profit = spread_width - max_risk

        # For iron condors (4 legs)
        elif len(legs) == 4 and "CONDOR" in strategy_type.upper():
            # Iron condor: 2 spreads, credit received, max loss is wider spread width minus credit
            max_profit = limit_price * 100  # Total credit

            # Find the two spread widths
            put_legs = [leg for leg in legs if leg['right'] == 'P']
            call_legs = [leg for leg in legs if leg['right'] == 'C']

            put_strikes = sorted([leg['strike'] for leg in put_legs])
            call_strikes = sorted([leg['strike'] for leg in call_legs])

            put_spread_width = (put_strikes[1] - put_strikes[0]) * 100
            call_spread_width = (call_strikes[1] - call_strikes[0]) * 100

            # Max risk is the wider spread minus credit
            wider_spread = max(put_spread_width, call_spread_width)
            max_risk = wider_spread - max_profit

        else:
            # Default calculation for other strategies
            max_profit = limit_price * 100 if limit_price > 0 else 0
            max_risk = abs(limit_price) * 100 if limit_price < 0 else 500  # Default fallback

        return (max_risk, max_profit)
