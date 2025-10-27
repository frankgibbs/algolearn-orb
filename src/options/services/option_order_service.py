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
        time_in_force: str = "DAY",
        equity_holding_id: int = None
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
            equity_holding_id: Link to equity holding for covered calls/ratio spreads (optional)

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
        if not legs or len(legs) < 1:
            raise ValueError("legs is REQUIRED and must have at least 1 leg")
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
                legs=legs,
                equity_holding_id=equity_holding_id
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

    def close_position(
        self,
        opening_order_id: int,
        exit_reason: str = "MANUAL_CLOSE",
        limit_price: float = None
    ) -> Dict:
        """
        Close an existing option position by placing offsetting order

        Args:
            opening_order_id: Original position order ID (required)
            exit_reason: Reason for closing (default: "MANUAL_CLOSE")
            limit_price: Optional limit price (if None, calculates from market)

        Returns:
            Dict with keys: closing_order_id, status, message, limit_price, expected_pnl

        Raises:
            ValueError: If opening_order_id invalid
            RuntimeError: If position not found, not OPEN, missing quotes, or close fails
        """
        if not opening_order_id:
            raise ValueError("opening_order_id is REQUIRED")
        if not exit_reason:
            raise ValueError("exit_reason is REQUIRED")

        logger.info(f"Closing position {opening_order_id}: {exit_reason}")

        try:
            # 1. Get original position from database
            position = self.db_manager.get_position(opening_order_id)
            if not position:
                raise RuntimeError(f"Position not found: {opening_order_id}")

            # 2. Validate position is OPEN
            if position.status != "OPEN":
                raise RuntimeError(f"Position {opening_order_id} is not OPEN (status: {position.status})")

            # 3. Build offsetting legs (reverse BUY/SELL actions)
            offsetting_legs = []
            for leg in position.legs:
                offsetting_legs.append({
                    'action': 'SELL' if leg.action == 'BUY' else 'BUY',
                    'strike': leg.strike,
                    'right': leg.right,
                    'expiry': leg.expiry,
                    'quantity': leg.quantity
                })

            # 4. Get current market prices if limit_price not provided
            if limit_price is None:
                # Calculate current spread value from market - NO FALLBACKS
                current_value = 0.0
                for leg in position.legs:
                    quote = self.client.get_option_greeks(
                        symbol=position.symbol,
                        expiry=leg.expiry,
                        strike=leg.strike,
                        right=leg.right
                    )

                    # STRICT: No quote = cannot close
                    if not quote:
                        raise RuntimeError(
                            f"No quote available for {position.symbol} {leg.strike}{leg.right} exp:{leg.expiry}. "
                            f"Cannot calculate closing price - will not proceed."
                        )

                    # STRICT: Require valid bid and ask
                    bid = quote.get('bid')
                    ask = quote.get('ask')

                    if bid is None or ask is None:
                        raise RuntimeError(
                            f"Missing bid/ask for {position.symbol} {leg.strike}{leg.right} exp:{leg.expiry}. "
                            f"bid={bid}, ask={ask}. Cannot calculate closing price - will not proceed."
                        )

                    if bid <= 0 or ask <= 0:
                        raise RuntimeError(
                            f"Invalid bid/ask for {position.symbol} {leg.strike}{leg.right} exp:{leg.expiry}. "
                            f"bid={bid}, ask={ask}. Prices must be positive - will not proceed."
                        )

                    # Use mid price - both bid and ask validated above
                    leg_price = (bid + ask) / 2

                    # For closing: opposite of original action
                    if leg.action == 'BUY':
                        current_value += leg_price  # We'll sell this
                    else:
                        current_value -= leg_price  # We'll buy this

                # Add small buffer for fill (0.05)
                limit_price = abs(current_value) + 0.05
                logger.info(f"Calculated closing limit price: ${limit_price:.2f}")

            # 5. Place offsetting combo order
            order_result = self.client.place_combo_order(
                symbol=position.symbol,
                legs=offsetting_legs,
                limit_price=limit_price,
                action="BUY",  # Always BUY the combo
                time_in_force="DAY"
            )

            if not order_result:
                raise RuntimeError("IB order submission returned no result")

            closing_order_id = order_result.get('orderId')
            if not closing_order_id:
                raise RuntimeError("No order ID returned from IB for closing order")

            # 6. Update original position with closing_order_id
            self.db_manager.set_closing_order(
                opening_order_id=opening_order_id,
                closing_order_id=closing_order_id,
                exit_reason=exit_reason
            )

            # 7. Calculate expected P&L
            if position.is_credit_spread:
                expected_pnl = (position.net_credit * 100) - (limit_price * 100)
            else:
                expected_pnl = (limit_price * 100) - abs(position.net_credit * 100)

            logger.info(f"Closing order {closing_order_id} placed for position {opening_order_id}")

            return {
                'closing_order_id': closing_order_id,
                'opening_order_id': opening_order_id,
                'status': 'CLOSING_ORDER_PLACED',
                'message': f"Closing order {closing_order_id} placed for position {opening_order_id}",
                'limit_price': limit_price,
                'expected_pnl': expected_pnl,
                'exit_reason': exit_reason
            }

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            raise RuntimeError(f"Failed to close position: {str(e)}")

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
