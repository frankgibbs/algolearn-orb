"""
Relative Volume Service - Calculate and rank stocks by relative volume

Based on "A Profitable Day Trading Strategy for The U.S. Equity Market"
(Zarattini, Barbon, Aziz 2024 - Swiss Finance Institute Paper No. 24-98)

Key Insight: "Stocks in Play" (relative volume > 100%) are the critical filter
that transforms base 29% returns into 1,637% returns.

Relative Volume Formula:
    RV = Current Volume / 14-Day Average Volume
"""

from src import logger
from src.core.constants import (
    CONFIG_MIN_RELATIVE_VOLUME,
    CONFIG_RELATIVE_VOLUME_LOOKBACK,
    CONFIG_TOP_N_STOCKS
)
from src.stocks.models.opening_range import OpeningRange
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy import func


class RelativeVolumeService:
    """Service for calculating and ranking stocks by relative volume"""

    def __init__(self, application_context):
        """
        Initialize relative volume service

        Args:
            application_context: Application context with state_manager and database

        Raises:
            ValueError: If application_context is None
        """
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.state_manager = application_context.state_manager
        self.database_manager = application_context.database_manager
        self.application_context = application_context

    def calculate_relative_volume(self, symbol: str, current_volume: int) -> float:
        """
        Calculate relative volume for a symbol

        RV = Current Volume / 14-Day Average Volume

        Args:
            symbol: Stock symbol (required)
            current_volume: Current volume to compare (required)

        Returns:
            Relative volume ratio (e.g., 1.5 means 150% of average)

        Raises:
            ValueError: If symbol/current_volume is None or configs are missing
            RuntimeError: If unable to calculate average (insufficient data)
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if current_volume is None or current_volume < 0:
            raise ValueError(f"current_volume must be non-negative, got: {current_volume}")

        # Get and validate lookback period config
        lookback_days = self.state_manager.get_config_value(CONFIG_RELATIVE_VOLUME_LOOKBACK)
        if lookback_days is None:
            raise ValueError("RELATIVE_VOLUME_LOOKBACK is REQUIRED")

        try:
            lookback_days = int(lookback_days)
        except (ValueError, TypeError):
            raise ValueError(f"RELATIVE_VOLUME_LOOKBACK must be a valid integer, got: {lookback_days}")

        if lookback_days <= 0:
            raise ValueError(f"RELATIVE_VOLUME_LOOKBACK must be positive, got: {lookback_days}")

        # Get historical volumes from database
        historical_volumes = self._get_historical_volumes(symbol, lookback_days)

        if not historical_volumes:
            raise RuntimeError(
                f"No historical opening range data found for {symbol} "
                f"(need {lookback_days} days of history)"
            )

        # Calculate average
        avg_volume = sum(historical_volumes) / len(historical_volumes)

        if avg_volume == 0:
            logger.warning(f"Average volume is zero for {symbol}, returning 0.0")
            return 0.0

        # Calculate ratio
        relative_volume = current_volume / avg_volume

        logger.debug(
            f"Relative volume for {symbol}: {relative_volume:.2f}x "
            f"(current: {current_volume:,}, avg: {avg_volume:,.0f})"
        )

        return relative_volume

    def _get_historical_volumes(self, symbol: str, lookback_days: int) -> List[int]:
        """
        Get historical opening range volumes from database

        Args:
            symbol: Stock symbol
            lookback_days: Number of days to look back

        Returns:
            List of volume values (may be empty if no data or volume field not yet added)
        """
        # Calculate date range
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=lookback_days)

        session = self.database_manager.get_session()
        try:
            # Query opening ranges for this symbol in the date range
            ranges = session.query(OpeningRange).filter(
                OpeningRange.symbol == symbol,
                OpeningRange.date >= start_date,
                OpeningRange.date < end_date
            ).all()

            # Extract volumes (handle case where volume field might not exist yet)
            volumes = []
            for range_obj in ranges:
                if hasattr(range_obj, 'volume') and range_obj.volume is not None:
                    volumes.append(range_obj.volume)

            logger.debug(
                f"Found {len(volumes)} historical volume entries for {symbol} "
                f"({start_date} to {end_date})"
            )

            return volumes

        finally:
            session.close()

    def rank_by_relative_volume(
        self,
        candidates: List[Dict],
        volume_key: str = 'volume'
    ) -> List[Dict]:
        """
        Rank candidates by relative volume and filter to top N

        Args:
            candidates: List of candidate dicts with symbol and volume
            volume_key: Key to access volume in candidate dict (default: 'volume')

        Returns:
            List of candidates sorted by relative volume (descending), filtered to top N,
            with 'relative_volume' and 'rank' fields added

        Raises:
            ValueError: If candidates is None or configs are missing
        """
        if candidates is None:
            raise ValueError("candidates is REQUIRED")

        if not candidates:
            logger.warning("No candidates provided for ranking")
            return []

        # Get configs
        min_relative_volume = self.state_manager.get_config_value(CONFIG_MIN_RELATIVE_VOLUME)
        if min_relative_volume is None:
            raise ValueError("MIN_RELATIVE_VOLUME is REQUIRED")

        top_n = self.state_manager.get_config_value(CONFIG_TOP_N_STOCKS)
        if top_n is None:
            raise ValueError("TOP_N_STOCKS is REQUIRED")

        try:
            min_relative_volume = float(min_relative_volume)
            top_n = int(top_n)
        except (ValueError, TypeError):
            raise ValueError(
                f"Invalid config values - MIN_RELATIVE_VOLUME: {min_relative_volume}, "
                f"TOP_N_STOCKS: {top_n}"
            )

        logger.info(
            f"Ranking {len(candidates)} candidates by relative volume "
            f"(min: {min_relative_volume}x, top: {top_n})"
        )

        # Calculate relative volume for each candidate
        ranked_candidates = []
        for candidate in candidates:
            symbol = candidate.get('symbol')
            volume = candidate.get(volume_key)

            if not symbol:
                logger.warning("Candidate missing symbol, skipping")
                continue

            if volume is None or volume <= 0:
                logger.warning(f"Candidate {symbol} has invalid volume: {volume}, skipping")
                continue

            try:
                relative_volume = self.calculate_relative_volume(symbol, volume)

                # Add relative volume to candidate dict
                enriched_candidate = candidate.copy()
                enriched_candidate['relative_volume'] = relative_volume
                ranked_candidates.append(enriched_candidate)

            except (ValueError, RuntimeError) as e:
                logger.warning(f"Could not calculate relative volume for {symbol}: {e}")
                # Skip candidates we can't calculate relative volume for
                continue

        # Filter by minimum threshold
        filtered_candidates = [
            c for c in ranked_candidates
            if c['relative_volume'] >= min_relative_volume
        ]

        logger.info(
            f"Filtered to {len(filtered_candidates)} candidates with "
            f"relative volume >= {min_relative_volume}x"
        )

        # Sort by relative volume (descending)
        sorted_candidates = sorted(
            filtered_candidates,
            key=lambda c: c['relative_volume'],
            reverse=True
        )

        # Take top N
        top_candidates = sorted_candidates[:top_n]

        # Assign ranks
        for i, candidate in enumerate(top_candidates):
            candidate['rank'] = i + 1

        logger.info(f"Selected top {len(top_candidates)} stocks by relative volume")

        if top_candidates:
            logger.info("Top 5 by relative volume:")
            for candidate in top_candidates[:5]:
                logger.info(
                    f"  #{candidate['rank']}: {candidate['symbol']} "
                    f"(RV: {candidate['relative_volume']:.2f}x, "
                    f"volume: {candidate.get(volume_key, 0):,})"
                )

        return top_candidates

    def filter_stocks_in_play(
        self,
        candidates: List[Dict],
        volume_key: str = 'volume'
    ) -> List[str]:
        """
        Filter to "Stocks in Play" - those with relative volume > threshold

        Convenience method that returns just the symbols.

        Args:
            candidates: List of candidate dicts with symbol and volume
            volume_key: Key to access volume in candidate dict (default: 'volume')

        Returns:
            List of stock symbols that qualify as "Stocks in Play"
        """
        top_candidates = self.rank_by_relative_volume(candidates, volume_key)
        return [c['symbol'] for c in top_candidates]
