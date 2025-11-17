from src import logger
from src.stocks.models.position import Position
from src.core.constants import CONFIG_ORB_TIMEFRAME, FIELD_STOCK_MARGIN_REQUIREMENTS
from datetime import datetime, date
from sqlalchemy import func
import pytz

class StocksStrategyService:
    """Core strategy logic and database operations for stock trading"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.client = application_context.client
        self.state_manager = application_context.state_manager
        self.database_manager = application_context.database_manager
        self.application_context = application_context

    def get_candidates(self, date, selected_only=True):
        """
        Fetch stock candidates from database for given date

        Args:
            date: Date to query (required)
            selected_only: If True, only return selected candidates

        Returns:
            List of candidate records

        Raises:
            ValueError: If date is None
            RuntimeError: If no candidates found
        """
        if date is None:
            raise ValueError("date is REQUIRED")

        logger.info(f"Fetching candidates for {date}, selected_only={selected_only}")

        candidates = self.database_manager.get_candidates(date, selected_only)

        if not candidates:
            raise RuntimeError(f"No candidates found for {date}")

        return candidates

    def save_candidates(self, candidates, scan_time):
        """
        Save stock candidates to database

        Args:
            candidates: List of candidate data (required)
            scan_time: Timestamp of scan (required)

        Raises:
            ValueError: If candidates is None or scan_time is None
        """
        if candidates is None:
            raise ValueError("candidates is REQUIRED")
        if scan_time is None:
            raise ValueError("scan_time is REQUIRED")

        logger.info(f"Saving {len(candidates)} candidates to database")

        self.database_manager.save_candidates(candidates, scan_time.date())

    def get_opening_range(self, symbol, date):
        """
        Fetch opening range from database

        Args:
            symbol: Stock symbol (required)
            date: Date to query (required)

        Returns:
            Opening range record with range_high, range_low, etc.

        Raises:
            ValueError: If symbol or date is None
            RuntimeError: If no opening range found
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if date is None:
            raise ValueError("date is REQUIRED")

        logger.info(f"Fetching opening range for {symbol} on {date}")

        opening_range = self.database_manager.get_opening_range(symbol, date)

        if opening_range is None:
            raise RuntimeError(f"No opening range found for {symbol} on {date}")

        return opening_range

    def save_opening_range(self, symbol, date, timeframe_minutes, range_high, range_low, range_size, range_size_pct, directional_bias=None, volume=None):
        """
        Save opening range to database

        Args:
            symbol: Stock symbol (required)
            date: Date of range (required)
            timeframe_minutes: Timeframe in minutes - 5, 15, 30, or 60 (required)
            range_high: High of opening range (required)
            range_low: Low of opening range (required)
            range_size: Absolute size of range (required)
            range_size_pct: Percentage size of range (required)
            directional_bias: Opening momentum direction - BULLISH or BEARISH (optional)
            volume: Total volume during opening range period (optional)

        Raises:
            ValueError: If any parameter is None or invalid
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if date is None:
            raise ValueError("date is REQUIRED")
        if timeframe_minutes is None:
            raise ValueError("timeframe_minutes is REQUIRED")
        if timeframe_minutes not in [5, 15, 30, 60]:
            raise ValueError("timeframe_minutes must be 5, 15, 30, or 60")
        if range_high is None:
            raise ValueError("range_high is REQUIRED")
        if range_low is None:
            raise ValueError("range_low is REQUIRED")
        if range_size is None:
            raise ValueError("range_size is REQUIRED")
        if range_size_pct is None:
            raise ValueError("range_size_pct is REQUIRED")

        # Validate range values
        if range_high <= range_low:
            raise ValueError(f"Invalid range: high ({range_high}) must be > low ({range_low})")
        if range_size <= 0:
            raise ValueError(f"Invalid range_size: {range_size}")
        if range_size_pct <= 0:
            raise ValueError(f"Invalid range_size_pct: {range_size_pct}")

        log_msg = f"Saving opening range for {symbol}: ${range_low:.2f}-${range_high:.2f} ({range_size_pct:.1f}%)"
        if directional_bias:
            log_msg += f", bias: {directional_bias}"
        if volume:
            log_msg += f", volume: {volume:,}"
        logger.info(log_msg)

        self.database_manager.save_opening_range(
            symbol, date, timeframe_minutes, range_high, range_low, range_size, range_size_pct,
            directional_bias=directional_bias,
            volume=volume
        )

    def fetch_historical_bars(self, contract, duration, bar_size):
        """
        Fetch historical bars from IB

        Args:
            contract: IB contract (required)
            duration: Duration string like "30 M" (required)
            bar_size: Bar size like "1 min" (required)

        Returns:
            List of bar data

        Raises:
            ValueError: If any parameter is None
            RuntimeError: If no data received
        """
        if contract is None:
            raise ValueError("contract is REQUIRED")
        if not duration:
            raise ValueError("duration is REQUIRED")
        if not bar_size:
            raise ValueError("bar_size is REQUIRED")

        logger.info(f"Fetching {duration} of {bar_size} bars for {contract.symbol}")

        # TODO: Implement actual IB historical data request
        # Placeholder for now
        bars = []

        if not bars:
            raise RuntimeError(f"No historical data received for {contract.symbol}")

        return bars

    def calculate_range(self, bars, start_time=None, end_time=None):
        """
        Calculate high/low range from bars within time window

        Args:
            bars: List of bar data from IB (required)
            start_time: Start time filter (optional, not used for single bar)
            end_time: End time filter (optional, not used for single bar)

        Returns:
            Dict with range_high, range_low, range_size, range_size_pct

        Raises:
            ValueError: If bars is None or empty
        """
        if bars is None or bars.empty:
            raise ValueError("bars is REQUIRED and cannot be empty")

        # Extract bar time information
        if len(bars) == 1:
            # Single bar - use its high/low directly
            bar = bars.iloc[0]
            bar_time = bar['date']
            range_high = float(bar['high'])
            range_low = float(bar['low'])
        else:
            # Multiple bars - find overall high/low and use first bar's time
            bar_time = bars.iloc[0]['date']
            range_high = float(bars['high'].max())
            range_low = float(bars['low'].min())

        logger.info(f"Calculating range from {len(bars)} bars at {bar_time}")

        # Calculate derived values
        range_size = range_high - range_low

        # Calculate percentage based on the midpoint
        range_mid = (range_high + range_low) / 2
        range_size_pct = (range_size / range_mid) * 100

        logger.info(f"Range calculated: ${range_low:.2f}-${range_high:.2f} "
                   f"(size: ${range_size:.2f}, {range_size_pct:.2f}%)")

        return {
            'range_high': range_high,
            'range_low': range_low,
            'range_size': range_size,
            'range_size_pct': range_size_pct,
            'range_mid': range_mid,
            'bar_count': len(bars),
            'bar_time': bar_time
        }

    def check_breakout_conditions(self, candidate, current_price, opening_range):
        """
        Check if stock has broken out of opening range

        Args:
            candidate: Candidate record (required)
            current_price: Current market price (required)
            opening_range: Opening range data (required)

        Returns:
            Dict with breakout info: {direction, confidence, reasoning}

        Raises:
            ValueError: If any parameter is None
        """
        if candidate is None:
            raise ValueError("candidate is REQUIRED")
        if current_price is None:
            raise ValueError("current_price is REQUIRED")
        if opening_range is None:
            raise ValueError("opening_range is REQUIRED")

        # TODO: Implement actual breakout logic
        logger.info(f"Checking breakout conditions for {candidate} at ${current_price}")

        # Placeholder logic
        return {
            'direction': 'NONE',
            'confidence': 0,
            'reasoning': 'Placeholder implementation'
        }

    def validate_market_conditions(self):
        """
        Validate current market conditions for trading

        Returns:
            Boolean indicating if conditions are favorable
        """
        # TODO: Implement market internals validation
        logger.info("Validating market conditions")

        # Placeholder - always return True for now
        return True

    def prepare_trade_parameters(self, candidate, breakout_info):
        """
        Prepare parameters for trade execution

        Args:
            candidate: Candidate record (required)
            breakout_info: Breakout analysis result (required)

        Returns:
            Dict with trade parameters

        Raises:
            ValueError: If any parameter is None
        """
        if candidate is None:
            raise ValueError("candidate is REQUIRED")
        if breakout_info is None:
            raise ValueError("breakout_info is REQUIRED")

        # TODO: Implement actual trade parameter calculation
        logger.info(f"Preparing trade parameters for {candidate}")

        # Placeholder parameters
        return {
            'symbol': 'PLACEHOLDER',
            'action': breakout_info.get('direction', 'NONE'),
            'entry_price': 100.0,
            'stop_loss': 99.0,
            'take_profit': 102.0,
            'confidence': breakout_info.get('confidence', 0)
        }

    def calculate_opening_range(self, symbol, timeframe_minutes):
        """
        Calculate opening range for a symbol

        Args:
            symbol: Stock symbol (required)
            timeframe_minutes: Timeframe in minutes - 15, 30, or 60 (required)

        Returns:
            Dict with opening range data: {
                'symbol': str,
                'range_high': float,
                'range_low': float,
                'range_mid': float,
                'range_size': float,
                'range_pct': float,
                'valid': bool,
                'reason': str  # If invalid
            }

        Raises:
            ValueError: If symbol or timeframe_minutes is None
            RuntimeError: If data fetch fails
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if timeframe_minutes is None:
            raise ValueError("timeframe_minutes is REQUIRED")
        if timeframe_minutes not in [15, 30, 60]:
            raise ValueError("timeframe_minutes must be 15, 30, or 60")

        logger.info(f"Calculating {timeframe_minutes}m opening range for {symbol}")

        # Calculate how many minutes since market open
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)
        today = now.date()
        market_open = datetime.combine(today, datetime.min.time().replace(hour=9, minute=30))
        market_open = pacific_tz.localize(market_open)

        # Calculate minutes since open
        minutes_since_open = int((now - market_open).total_seconds() / 60)

        # Need to fetch enough bars to include the opening range
        # Add buffer to ensure we get the opening bars
        duration_to_fetch = max(minutes_since_open + timeframe_minutes, timeframe_minutes * 2)

        # Fetch bars (this will get bars from "now" going backwards)
        bar_size = f"{timeframe_minutes} mins"
        bars = self.client.get_stock_bars(
            symbol=symbol,
            duration_minutes=duration_to_fetch,
            bar_size=bar_size,
            timeout=10
        )

        if bars is None or bars.empty:
            raise RuntimeError(f"No historical data received for {symbol}")

        # Use only the FIRST bar (which is the opening range bar)
        # The bars are returned chronologically, so first bar = earliest = opening range
        opening_bar = bars.iloc[0:1]  # Get first bar only

        # Calculate range from the opening bar
        range_data = self.calculate_range(opening_bar)

        # Validate range
        from src.stocks.stocks_config import get_stock_config
        stock_config = get_stock_config(symbol)
        is_valid = self._validate_range_percentage(range_data['range_size_pct'], stock_config)

        return {
            'symbol': symbol,
            'range_high': range_data['range_high'],
            'range_low': range_data['range_low'],
            'range_mid': range_data['range_mid'],
            'range_size': range_data['range_size'],
            'range_pct': range_data['range_size_pct'],
            'valid': is_valid,
            'reason': 'Valid range' if is_valid else f"Range {range_data['range_size_pct']:.1f}% outside bounds"
        }

    def check_breakout_signal(self, symbol, opening_range, current_price, previous_close):
        """
        Check if breakout conditions are met

        Args:
            symbol: Stock symbol (required)
            opening_range: Opening range data (required)
            current_price: Current market price (required)
            previous_close: Previous candle close price (required)

        Returns:
            Dict with breakout info: {
                'signal': 'LONG'|'SHORT'|'NONE',
                'entry_price': float,
                'stop_loss': float,
                'take_profit': float,
                'range_size': float
            }

        Raises:
            ValueError: If any parameter is None
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if opening_range is None:
            raise ValueError("opening_range is REQUIRED")
        if current_price is None:
            raise ValueError("current_price is REQUIRED")
        if previous_close is None:
            raise ValueError("previous_close is REQUIRED")

        logger.info(f"Checking breakout signal for {symbol} at ${current_price}")

        range_high = opening_range.range_high
        range_low = opening_range.range_low
        range_mid = (range_high + range_low) / 2
        range_size = range_high - range_low

        # Academic ORB Strategy: No take-profit targets
        # Positions exit via ATR-based stops or EOD profitable closure only

        signal = 'NONE'
        entry_price = current_price
        stop_loss = None

        # Check for long breakout (close above range high)
        if previous_close > range_high:
            signal = 'LONG'
            stop_loss = range_mid  # Stop at range midpoint

        # Check for short breakout (close below range low)
        elif previous_close < range_low:
            signal = 'SHORT'
            stop_loss = range_mid  # Stop at range midpoint

        logger.info(f"Breakout signal for {symbol}: {signal}")

        return {
            'signal': signal,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': None,  # Academic strategy: no take-profit
            'range_size': range_size
        }

    def calculate_position_parameters(self, signal_info, account_value, risk_pct):
        """
        Calculate position size and risk parameters (Academic ORB Strategy)

        No take-profit targets - positions exit via ATR-based stops or EOD closure only.

        Args:
            signal_info: Signal information dict (required)
            account_value: Total account value (required)
            risk_pct: Risk percentage per trade (required)

        Returns:
            Dict with position parameters: {
                'shares': int,
                'risk_amount': float
            }

        Raises:
            ValueError: If any parameter is None or invalid
        """
        if signal_info is None:
            raise ValueError("signal_info is REQUIRED")
        if account_value is None or account_value <= 0:
            raise ValueError("account_value is REQUIRED and must be > 0")
        if risk_pct is None or risk_pct <= 0:
            raise ValueError("risk_pct is REQUIRED and must be > 0")

        entry_price = signal_info['entry_price']
        stop_loss = signal_info['stop_loss']

        if entry_price is None or stop_loss is None:
            raise ValueError("signal_info must contain entry_price and stop_loss")

        # Calculate risk amount per share
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0:
            raise ValueError("Risk per share cannot be zero")

        # Calculate position size based on account risk
        total_risk_amount = account_value * (risk_pct / 100)
        shares = int(total_risk_amount / risk_per_share)

        # Academic strategy: No take-profit, no R/R ratio calculation
        logger.info(f"Position parameters: {shares} shares, risk ${total_risk_amount:.2f}")

        return {
            'shares': shares,
            'risk_amount': total_risk_amount
        }

    def _validate_range_percentage(self, range_size_pct, stock_config):
        """
        Validate if range size percentage is within acceptable bounds

        Args:
            range_size_pct: Range size as percentage (required)
            stock_config: Stock configuration dict (required)

        Returns:
            Boolean indicating if range is valid

        Raises:
            ValueError: If any parameter is None
        """
        if range_size_pct is None:
            raise ValueError("range_size_pct is REQUIRED")
        if stock_config is None:
            raise ValueError("stock_config is REQUIRED")

        min_pct = stock_config['min_range_pct']
        max_pct = stock_config['max_range_pct']

        return min_pct <= range_size_pct <= max_pct

    def get_open_positions_count(self):
        """
        Get count of currently open positions

        Returns:
            Integer count of open positions

        Raises:
            RuntimeError: If database query fails
        """
        # Query positions with status 'OPEN' or 'PENDING'
        # Let exceptions propagate per CLAUDE.md pattern
        session = self.database_manager.get_session()
        try:
            open_positions = session.query(Position).filter(
                Position.status.in_(['OPEN', 'PENDING'])
            ).count()

            logger.debug(f"Current open positions count: {open_positions}")
            return open_positions
        finally:
            session.close()

    def has_open_position(self, symbol):
        """
        Check if a specific symbol has any open or pending positions

        Args:
            symbol: Stock symbol to check (required)

        Returns:
            Boolean indicating if symbol has open/pending positions

        Raises:
            ValueError: If symbol is None or empty
            RuntimeError: If database query fails
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        # Query positions for this specific symbol with status 'OPEN' or 'PENDING'
        # Let exceptions propagate per CLAUDE.md pattern
        session = self.database_manager.get_session()
        try:
            position_count = session.query(Position).filter(
                Position.symbol == symbol,
                Position.status.in_(['OPEN', 'PENDING'])
            ).count()

            has_position = position_count > 0
            logger.debug(f"Symbol {symbol} has open/pending positions: {has_position}")
            return has_position
        finally:
            session.close()

    def has_position_today(self, symbol):
        """
        Check if a specific symbol has any position (PENDING, OPEN, or CLOSED) today

        Args:
            symbol: Stock symbol to check (required)

        Returns:
            Boolean indicating if symbol has any position today

        Raises:
            ValueError: If symbol is None or empty
            RuntimeError: If database query fails
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        # Query positions for this specific symbol created today (any status)
        # Let exceptions propagate per CLAUDE.md pattern
        session = self.database_manager.get_session()
        try:
            today = date.today()

            position_count = session.query(Position).filter(
                Position.symbol == symbol,
                func.date(Position.entry_time) == today
            ).count()

            has_position = position_count > 0
            logger.debug(f"Symbol {symbol} has positions today: {has_position}")
            return has_position
        finally:
            session.close()

    def get_margin_requirements(self):
        """
        Get margin requirements from database

        Returns:
            List of dicts with symbol, margin, and metadata for each stock

        Raises:
            RuntimeError: If margin data cannot be retrieved
        """
        # Get all margins from database
        margins = self.database_manager.get_all_margins()

        result = []
        for margin in margins:
            result.append({
                'symbol': margin.symbol,
                'margin_per_share': margin.margin_per_share,
                'synthetic': margin.synthetic,
                'last_updated': margin.last_updated.isoformat() if margin.last_updated else 'N/A'
            })

        logger.debug(f"Retrieved margin requirements for {len(result)} stocks from database")
        return result

    # Telegram command support methods

    def get_plot_data(self, symbol):
        """
        Get OHLC data and opening range for plotting

        Args:
            symbol: Stock symbol (required)

        Returns:
            Tuple of (DataFrame with OHLC data, OpeningRange object or None)

        Raises:
            ValueError: If symbol is None
            RuntimeError: If no data available
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        logger.info(f"Getting plot data for {symbol}")

        # Get timeframe from config
        timeframe = self.state_manager.get_config_value(CONFIG_ORB_TIMEFRAME)
        if timeframe is None:
            timeframe = 30  # Default to 30 minutes

        # Get data for full trading day with specified timeframe
        bars = self.client.get_stock_bars(
            symbol=symbol,
            duration_minutes=390,  # Full trading day (6.5 hours)
            bar_size=f"{timeframe} mins"
        )

        if bars is None or bars.empty:
            raise RuntimeError(f"No data available for {symbol}")

        # Get opening range for today - allow None if not found
        from datetime import date
        try:
            opening_range = self.get_opening_range(symbol, date.today())
            # Log the opening range details for debugging
            logger.info(f"Using opening range for {symbol}: date={opening_range.date}, "
                        f"high={opening_range.range_high}, low={opening_range.range_low}")
        except RuntimeError as e:
            # No opening range found - chart will render without support/resistance lines
            logger.info(f"No opening range found for {symbol}, chart will render without support/resistance lines")
            opening_range = None

        return bars, opening_range

    def get_opening_ranges_summary(self, date=None):
        """
        Get today's opening ranges for display

        Args:
            date: Date to query (optional, defaults to today)

        Returns:
            List of dicts with symbol and range_pct
        """
        if date is None:
            date = datetime.now(pytz.timezone('US/Pacific')).date()

        logger.info(f"Getting opening ranges for {date}")

        # Query database for opening ranges
        ranges = self.database_manager.get_opening_ranges_by_date(date)

        result = []
        for r in ranges:
            result.append({
                'symbol': r.symbol,
                'range_pct': r.range_size_pct
            })

        return result

    def get_positions_pnl(self):
        """
        Get P&L for all open positions

        Returns:
            List of dicts with position data and current P&L
        """
        logger.info("Getting positions P&L")

        # Get open positions from database
        open_positions = self.database_manager.get_open_positions()

        result = []
        for p in open_positions:
            try:
                # Get current price from IB
                current_price = self.client.get_stock_price(p.symbol)

                if current_price is None:
                    logger.warning(f"Could not get current price for {p.symbol}")
                    current_price = p.entry_price  # Fallback to entry price

                # Calculate unrealized P&L
                if p.direction == 'LONG':
                    unrealized_pnl = (current_price - p.entry_price) * p.shares
                else:  # SHORT
                    unrealized_pnl = (p.entry_price - current_price) * p.shares

                # Calculate locked P&L (worst case exit at current stop)
                if p.direction == 'LONG':
                    locked_pnl = (p.current_stop_price - p.entry_price) * p.shares
                else:  # SHORT
                    locked_pnl = (p.entry_price - p.current_stop_price) * p.shares

                result.append({
                    'symbol': p.symbol,
                    'direction': p.direction,
                    'shares': p.shares,
                    'entry_price': p.entry_price,
                    'current_price': current_price,
                    'unrealized_pnl': unrealized_pnl,
                    'locked_pnl': locked_pnl
                })

            except Exception as e:
                logger.error(f"Error calculating P&L for {p.symbol}: {e}")
                # Add position with zero P&L on error
                # Calculate locked P&L even on error (we have entry and stop data)
                if p.direction == 'LONG':
                    locked_pnl = (p.current_stop_price - p.entry_price) * p.shares
                else:  # SHORT
                    locked_pnl = (p.entry_price - p.current_stop_price) * p.shares

                result.append({
                    'symbol': p.symbol,
                    'direction': p.direction,
                    'shares': p.shares,
                    'entry_price': p.entry_price,
                    'current_price': p.entry_price,
                    'unrealized_pnl': 0.0,
                    'locked_pnl': locked_pnl
                })

        return result

    def get_open_orders_summary(self):
        """
        Get summary of open orders from IB

        Returns:
            List of dicts with order information
        """
        logger.info("Getting open orders summary")

        try:
            # Get orders from IB
            ib_orders = self.client.get_open_orders()

            result = []
            for order_id, order_data in ib_orders.items():
                # Extract contract symbol
                contract = order_data.get('contract')
                symbol = 'N/A'
                if contract and hasattr(contract, 'symbol'):
                    symbol = contract.symbol

                result.append({
                    'order_id': order_data.get('orderId', order_id),
                    'symbol': symbol,
                    'action': order_data.get('action', 'N/A'),
                    'quantity': order_data.get('totalQuantity', 0),
                    'type': order_data.get('orderType', 'N/A'),
                    'status': order_data.get('orderState', 'N/A')
                })

            return result

        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []

    def format_ranges_table(self, ranges):
        """
        Format opening ranges data as HTML table for Telegram

        Args:
            ranges: List of dicts with 'symbol' and 'range_size_pct' or 'range_pct' keys

        Returns:
            String with formatted HTML table
        """
        from prettytable import PrettyTable

        if not ranges:
            return "No ranges available"

        # Create PrettyTable
        table = PrettyTable()
        table.field_names = ["Symbol", "Range %"]
        table.align["Symbol"] = "l"
        table.align["Range %"] = "r"

        # Add rows for each range
        for range_data in ranges:
            # Handle both 'range_size_pct' (from command) and 'range_pct' (from database)
            pct = range_data.get('range_size_pct') or range_data.get('range_pct', 0)
            table.add_row([range_data['symbol'], f"{pct:.1f}%"])

        return f"<pre><code>{table}</code></pre>"