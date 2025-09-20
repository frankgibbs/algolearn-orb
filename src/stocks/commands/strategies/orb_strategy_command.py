from src.core.command import Command
from src.core.constants import *
from src.stocks.services.stocks_strategy_service import StocksStrategyService
from src import logger
import pytz
from datetime import datetime

class ORBStrategyCommand(Command):
    """
    Opening Range Breakout Strategy Command
    Monitors for breakouts and executes trades when conditions are met
    """

    def execute(self, event):
        """
        Execute ORB strategy check

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.info("Executing ORB strategy check")

        # Validate timing
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        if not self._is_valid_trading_time(now):
            logger.warning(f"ORB strategy called outside trading hours: {now}")
            return

        # Initialize service
        strategy_service = StocksStrategyService(self.application_context)

        # Get candidates and opening ranges from database
        try:
            candidates = strategy_service.get_candidates(
                date=now.date(),
                selected_only=True
            )
        except RuntimeError as e:
            logger.info(f"No candidates available for ORB strategy: {e}")
            return

        logger.info(f"Analyzing {len(candidates)} candidates for ORB opportunities")

        # Check each candidate for breakout conditions
        signals_generated = 0
        for candidate in candidates:
            try:
                if self._analyze_candidate_for_breakout(candidate, strategy_service, now):
                    signals_generated += 1
            except Exception as e:
                logger.error(f"Error analyzing candidate {candidate}: {e}")
                # Continue with other candidates

        logger.info(f"ORB strategy check complete. Generated {signals_generated} signals")

    def _analyze_candidate_for_breakout(self, candidate, strategy_service, now):
        """
        Analyze a single candidate for breakout conditions

        Args:
            candidate: Candidate record (required)
            strategy_service: Strategy service instance (required)
            now: Current datetime (required)

        Returns:
            Boolean indicating if a signal was generated

        Raises:
            ValueError: If any parameter is None
        """
        if candidate is None:
            raise ValueError("candidate is REQUIRED")
        if strategy_service is None:
            raise ValueError("strategy_service is REQUIRED")
        if now is None:
            raise ValueError("now is REQUIRED")

        # TODO: Get actual symbol from candidate
        symbol = getattr(candidate, 'symbol', 'PLACEHOLDER')

        try:
            # Get opening range for this candidate
            opening_range = strategy_service.get_opening_range(symbol, now.date())
        except RuntimeError as e:
            logger.warning(f"No opening range found for {symbol}: {e}")
            return False

        # TODO: Get current market price from IB
        current_price = None
        if current_price is None:
            logger.warning(f"Cannot get current price for {symbol}")
            return False

        # Check breakout conditions
        breakout_info = strategy_service.check_breakout_conditions(
            candidate=candidate,
            current_price=current_price,
            opening_range=opening_range
        )

        # Validate market conditions
        if breakout_info['direction'] != 'NONE':
            if not strategy_service.validate_market_conditions():
                logger.info(f"Market conditions not favorable for {symbol} breakout")
                return False

            # Check position limits
            if not self._check_position_limits():
                logger.info(f"Position limits reached, skipping {symbol}")
                return False

            # Generate trade signal
            self._generate_trade_signal(candidate, breakout_info, strategy_service)
            return True

        return False

    def _check_position_limits(self):
        """
        Check if we can open new positions based on configured limits

        Returns:
            Boolean indicating if new positions can be opened
        """
        max_positions = self.state_manager.get_config_value(CONFIG_MAX_POSITIONS)
        if max_positions is None:
            raise ValueError("CONFIG_MAX_POSITIONS not configured")

        # TODO: Get current open position count from database
        current_positions = 0

        return current_positions < max_positions

    def _generate_trade_signal(self, candidate, breakout_info, strategy_service):
        """
        Generate trade signal for execution

        Args:
            candidate: Candidate record (required)
            breakout_info: Breakout analysis result (required)
            strategy_service: Strategy service instance (required)

        Raises:
            ValueError: If any parameter is None
        """
        if candidate is None:
            raise ValueError("candidate is REQUIRED")
        if breakout_info is None:
            raise ValueError("breakout_info is REQUIRED")
        if strategy_service is None:
            raise ValueError("strategy_service is REQUIRED")

        # Prepare trade parameters
        trade_params = strategy_service.prepare_trade_parameters(candidate, breakout_info)

        # TODO: Execute trade via execution service
        # For now, just log the signal
        symbol = trade_params.get('symbol', 'UNKNOWN')
        action = trade_params.get('action', 'NONE')
        confidence = trade_params.get('confidence', 0)

        logger.info(f"ORB Signal Generated: {action} {symbol} (confidence: {confidence}%)")

        # Send Telegram notification
        self.state_manager.sendTelegramMessage(
            f"🚀 ORB Signal: {action} {symbol}\n"
            f"Confidence: {confidence}%\n"
            f"Reason: {breakout_info.get('reasoning', 'N/A')}"
        )

    def _is_valid_trading_time(self, now):
        """
        Check if current time is valid for ORB trading

        Args:
            now: Current datetime in Pacific timezone (required)

        Returns:
            Boolean indicating if timing is valid for trading

        Raises:
            ValueError: If now is None
        """
        if now is None:
            raise ValueError("now is REQUIRED")

        # Valid trading window: 7:00 AM - 12:00 PM PST
        hour = now.hour
        return 7 <= hour < 13