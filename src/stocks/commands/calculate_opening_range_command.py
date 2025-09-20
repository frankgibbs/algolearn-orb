from src.core.command import Command
from src.core.constants import *
from src.stocks.services.stocks_strategy_service import StocksStrategyService
from src import logger
import pytz
from datetime import datetime

class CalculateOpeningRangeCommand(Command):
    """Calculate opening range at 7:00 AM PST (10:00 AM ET)"""

    def execute(self, event):
        """
        Calculate opening range for all candidates

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.info("Calculating opening ranges for ORB candidates")

        # Validate timing
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        if not self._is_valid_calculation_time(now):
            raise RuntimeError(f"Opening range calculation called at invalid time: {now}")

        # Initialize service
        strategy_service = StocksStrategyService(self.application_context)

        # Get today's candidates from database
        try:
            candidates = strategy_service.get_candidates(
                date=now.date(),
                selected_only=True
            )
        except RuntimeError as e:
            logger.warning(f"No candidates found for opening range calculation: {e}")
            return

        logger.info(f"Calculating opening ranges for {len(candidates)} candidates")

        # Process each candidate
        ranges_calculated = 0
        for candidate in candidates:
            try:
                self._calculate_range_for_candidate(candidate, strategy_service, now)
                ranges_calculated += 1
            except Exception as e:
                logger.error(f"Failed to calculate range for {candidate}: {e}")
                # Continue with other candidates

        # Send notification
        self.state_manager.sendTelegramMessage(
            f"📏 Opening ranges calculated at {now.strftime('%I:%M %p PST')}\n"
            f"Successfully calculated {ranges_calculated}/{len(candidates)} ranges"
        )

    def _calculate_range_for_candidate(self, candidate, strategy_service, now):
        """
        Calculate opening range for a single candidate

        Args:
            candidate: Candidate record (required)
            strategy_service: Strategy service instance (required)
            now: Current datetime (required)

        Raises:
            ValueError: If any parameter is None
            RuntimeError: If calculation fails
        """
        if candidate is None:
            raise ValueError("candidate is REQUIRED")
        if strategy_service is None:
            raise ValueError("strategy_service is REQUIRED")
        if now is None:
            raise ValueError("now is REQUIRED")

        # TODO: Get actual contract for candidate
        # For now, use placeholder
        symbol = getattr(candidate, 'symbol', 'PLACEHOLDER')

        logger.info(f"Calculating opening range for {symbol}")

        # Get ORB period from config
        orb_period = self.state_manager.get_config_value(CONFIG_ORB_PERIOD_MINUTES)
        if orb_period is None:
            raise ValueError("CONFIG_ORB_PERIOD_MINUTES not configured")

        # TODO: Fetch historical data for opening period (6:30-7:00 AM PST)
        # For now, use placeholder data
        bars = []

        if not bars:
            logger.warning(f"No bars received for {symbol}, skipping")
            return

        # Calculate range from bars
        range_data = strategy_service.calculate_range(bars)

        # Save to database
        strategy_service.save_opening_range(
            symbol=symbol,
            date=now.date(),
            range_high=range_data['range_high'],
            range_low=range_data['range_low'],
            range_size=range_data['range_size'],
            range_size_pct=range_data['range_size_pct']
        )

        logger.info(f"Opening range saved for {symbol}: "
                   f"${range_data['range_low']:.2f}-${range_data['range_high']:.2f} "
                   f"({range_data['range_size_pct']:.1f}%)")

    def _is_valid_calculation_time(self, now):
        """
        Check if current time is valid for opening range calculation

        Args:
            now: Current datetime in Pacific timezone (required)

        Returns:
            Boolean indicating if timing is valid

        Raises:
            ValueError: If now is None
        """
        if now is None:
            raise ValueError("now is REQUIRED")

        # Valid window: 7:00-7:05 AM PST (just after opening range period)
        hour = now.hour
        minute = now.minute

        return hour == 7 and minute <= 5