"""
OptionAnalyzerService - Exit analysis and position management recommendations

Analyzes open positions and provides actionable recommendations based on:
- % of max profit achieved
- Days to expiration
- Distance to breakeven
- IV changes
- Theta decay

Based on Tastytrade-style management rules.
"""

from src import logger
from datetime import datetime
from typing import Dict, Optional, List


class OptionAnalyzerService:
    """Service for analyzing option positions and recommending actions"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.application_context = application_context
        self.client = application_context.client
        self.db_manager = application_context.option_db_manager

    def analyze_position(self, order_id: int) -> Dict:
        """
        Analyze an option position and provide exit/management recommendation

        Args:
            order_id: Position ID (required)

        Returns:
            Dict with keys: recommendation, reason, metrics, suggested_action

        Raises:
            ValueError: If order_id is invalid
            RuntimeError: If position not found or analysis fails
        """
        if not order_id:
            raise ValueError("order_id is REQUIRED")

        logger.info(f"Analyzing position {order_id}")

        try:
            # Get position from database
            position = self.db_manager.get_position(order_id)
            if not position:
                raise RuntimeError(f"Position not found for order_id {order_id}")

            # NOTE: P&L calculation removed - should use get_option_quote MCP tool
            # This service needs refactoring to calculate P&L on-demand
            raise RuntimeError("OptionAnalyzerService temporarily disabled - use get_option_quote MCP tool for P&L analysis")

            # TODO: Refactor to calculate P&L using get_option_quote instead of storing it
            # dte = position.days_to_expiration

            # Get current IV to compare with entry IV
            current_iv = self._get_current_atm_iv(position.symbol)
            iv_change_pct = ((current_iv - position.entry_iv) / position.entry_iv * 100) if position.entry_iv > 0 else 0

            # Calculate distance to breakeven
            breakeven_distance = self._calculate_breakeven_distance(position)

            # Compile metrics
            metrics = {
                'symbol': position.symbol,
                'strategy_type': position.strategy_type,
                'dte': dte,
                'pct_of_max_profit': pct_of_max_profit,
                'unrealized_pnl': unrealized_pnl,
                'actual_roi': roi,
                'entry_iv': position.entry_iv,
                'current_iv': current_iv,
                'iv_change_pct': iv_change_pct,
                'breakeven_distance_pct': breakeven_distance,
                'max_risk': position.max_risk,
                'max_profit': position.max_profit
            }

            # Apply decision rules
            recommendation, reason, suggested_action = self._apply_decision_rules(metrics)

            logger.info(f"Position {order_id} analysis: {recommendation} - {reason}")

            return {
                'order_id': order_id,
                'recommendation': recommendation,
                'reason': reason,
                'suggested_action': suggested_action,
                'metrics': metrics,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error analyzing position: {e}")
            raise RuntimeError(f"Failed to analyze position: {str(e)}")

    def _apply_decision_rules(self, metrics: Dict) -> tuple:
        """
        Apply Tastytrade-style management rules

        Returns:
            Tuple of (recommendation, reason, suggested_action)
        """
        pct_profit = metrics['pct_of_max_profit']
        dte = metrics['dte']
        roi = metrics['actual_roi']
        breakeven_distance = metrics['breakeven_distance_pct']
        iv_change = metrics['iv_change_pct']

        # Rule 1: TAKE PROFIT - Achieved 50-75% of max profit
        if pct_profit >= 50:
            if pct_profit >= 75:
                return (
                    "TAKE_PROFIT_NOW",
                    f"Captured {pct_profit:.1f}% of max profit ({roi:.1f}% ROI). Excellent exit point.",
                    f"Close position for ${metrics['unrealized_pnl']:.2f} profit"
                )
            else:
                return (
                    "TAKE_PROFIT_SOON",
                    f"Captured {pct_profit:.1f}% of max profit ({roi:.1f}% ROI). Consider closing to lock in gains.",
                    f"Close position for ${metrics['unrealized_pnl']:.2f} profit or hold for more"
                )

        # Rule 2: MANAGE - Approaching expiration (21 DTE or less)
        if dte <= 21:
            if dte <= 7:
                return (
                    "CLOSE_OR_ROLL",
                    f"Only {dte} DTE remaining. Gamma risk increasing. Currently at {pct_profit:.1f}% of max profit.",
                    f"Close for ${metrics['unrealized_pnl']:.2f} or roll to next expiration"
                )
            else:
                return (
                    "MONITOR_CLOSELY",
                    f"{dte} DTE remaining. Monitor daily. Currently at {pct_profit:.1f}% of max profit.",
                    f"Prepare to close or roll within next week"
                )

        # Rule 3: DEFEND - Approaching or breaching breakeven
        if breakeven_distance < 5:
            if breakeven_distance < 2:
                return (
                    "CLOSE_NOW",
                    f"Price within {breakeven_distance:.1f}% of breakeven. High risk of loss. Cut losses.",
                    f"Close immediately to prevent max loss"
                )
            else:
                return (
                    "DEFEND",
                    f"Price within {breakeven_distance:.1f}% of breakeven. Consider closing or rolling.",
                    f"Close for ${metrics['unrealized_pnl']:.2f} loss or roll defensively"
                )

        # Rule 4: IV EXPANSION - Volatility increased significantly
        if iv_change > 25:
            return (
                "CONSIDER_EARLY_CLOSE",
                f"IV increased {iv_change:.1f}% since entry. Position may be under pressure. {pct_profit:.1f}% profit captured.",
                f"Close early at ${metrics['unrealized_pnl']:.2f} or wait for IV contraction"
            )

        # Rule 5: HOLD - Position is working as planned
        if pct_profit > 25:
            return (
                "HOLD_FOR_TARGET",
                f"Position profitable ({pct_profit:.1f}% of max, {roi:.1f}% ROI). {dte} DTE remaining. Let it work.",
                f"Hold until 50% profit target or {dte-7} DTE"
            )
        elif pct_profit > 0:
            return (
                "HOLD_AND_MONITOR",
                f"Small profit ({pct_profit:.1f}% of max). {dte} DTE remaining. Give it time.",
                f"Hold and monitor. Target is 50% of max profit."
            )
        else:
            return (
                "HOLD_WITH_CAUTION",
                f"Position at {pct_profit:.1f}% of max profit (${metrics['unrealized_pnl']:.2f} loss). {dte} DTE remaining.",
                f"Hold unless price approaches breakeven or DTE < 21"
            )

    def _get_current_atm_iv(self, symbol: str) -> float:
        """
        Get current ATM implied volatility for symbol

        Args:
            symbol: Stock symbol

        Returns:
            Current ATM IV as decimal

        Raises:
            RuntimeError: If IV cannot be retrieved
        """
        try:
            # Use volatility service to get current IV
            from src.stocks.services.volatility_service import VolatilityService
            vol_service = VolatilityService(self.application_context)
            iv_data = vol_service.get_current_atm_iv(symbol)
            return iv_data['atm_iv']
        except Exception as e:
            logger.warning(f"Could not get current IV for {symbol}: {e}")
            # Return a default value if IV unavailable
            return 0.30  # 30% default

    def _calculate_breakeven_distance(self, position) -> float:
        """
        Calculate distance from current price to breakeven as percentage

        Args:
            position: OptionPosition object

        Returns:
            Distance to breakeven as percentage
        """
        try:
            # Get current stock price
            current_price = self.client.get_stock_price(position.symbol)

            # Calculate breakeven based on strategy
            if position.strategy_type == "BULL_PUT_SPREAD":
                # Breakeven is short put strike - credit received
                short_leg = [leg for leg in position.legs if leg.action == "SELL"][0]
                breakeven = short_leg.strike - position.net_credit

                # Distance below current price
                distance_pct = ((current_price - breakeven) / current_price * 100)

            elif position.strategy_type == "BEAR_CALL_SPREAD":
                # Breakeven is short call strike + credit received
                short_leg = [leg for leg in position.legs if leg.action == "SELL"][0]
                breakeven = short_leg.strike + position.net_credit

                # Distance above current price
                distance_pct = ((breakeven - current_price) / current_price * 100)

            elif "IRON_CONDOR" in position.strategy_type or "IRON_BUTTERFLY" in position.strategy_type:
                # Two breakevens - check distance to nearest
                short_legs = [leg for leg in position.legs if leg.action == "SELL"]
                short_put = [leg for leg in short_legs if leg.right == "P"][0]
                short_call = [leg for leg in short_legs if leg.right == "C"][0]

                # Calculate both breakevens
                lower_breakeven = short_put.strike - (position.net_credit / 2)
                upper_breakeven = short_call.strike + (position.net_credit / 2)

                # Distance to nearest breakeven
                distance_to_lower = ((current_price - lower_breakeven) / current_price * 100)
                distance_to_upper = ((upper_breakeven - current_price) / current_price * 100)

                distance_pct = min(distance_to_lower, distance_to_upper)

            else:
                # Default calculation
                distance_pct = 10.0  # Default safe distance

            return distance_pct

        except Exception as e:
            logger.warning(f"Error calculating breakeven distance: {e}")
            return 10.0  # Default safe distance

    def analyze_all_positions(self, symbol: str = None) -> List[Dict]:
        """
        Analyze all open positions and provide recommendations

        Args:
            symbol: Optional symbol filter

        Returns:
            List of analysis results for each position

        Raises:
            RuntimeError: If analysis fails
        """
        logger.info(f"Analyzing all open positions{' for ' + symbol if symbol else ''}")

        try:
            # Get all open positions
            open_positions = self.db_manager.get_open_positions(symbol=symbol)

            results = []
            for position in open_positions:
                try:
                    analysis = self.analyze_position(position.id)
                    results.append(analysis)
                except Exception as e:
                    logger.warning(f"Error analyzing position {position.id}: {e}")
                    results.append({
                        'order_id': position.id,
                        'recommendation': "ERROR",
                        'reason': f"Analysis failed: {str(e)}",
                        'error': True
                    })

            logger.info(f"Analyzed {len(results)} positions")
            return results

        except Exception as e:
            logger.error(f"Error analyzing all positions: {e}")
            raise RuntimeError(f"Failed to analyze positions: {str(e)}")
