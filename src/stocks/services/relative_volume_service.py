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
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional
from sqlalchemy import func
import pytz


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
        self.client = application_context.client
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
        Get historical opening range volumes from IB real-time bars

        Fetches historical 5-minute bars and extracts opening range volume for each day.
        Opening range is the first 5-minute bar after market open (6:30 AM PST / 9:30 AM ET).

        Args:
            symbol: Stock symbol
            lookback_days: Number of trading days to look back (typically 14)

        Returns:
            List of opening range volume values for each trading day

        Raises:
            RuntimeError: If unable to fetch bars from IB or insufficient data
            TimeoutError: If IB request times out
        """
        # Fetch enough calendar days to ensure we get lookback_days of trading days
        # Use ~1.5x to account for weekends and holidays
        calendar_days = int(lookback_days * 1.5) + 3

        # Fetch 5-minute historical bars from IB (client will raise on errors)
        bars = self.client.get_stock_bars_extended(
            symbol=symbol,
            duration_days=calendar_days,
            bar_size="5 mins",
            timeout=30
        )

        if bars is None or bars.empty:
            raise RuntimeError(
                f"No historical bars received from IB for {symbol} "
                f"(requested {calendar_days} days of 5-minute bars)"
            )

        logger.debug(f"Fetched {len(bars)} 5-minute bars for {symbol} ({calendar_days} days)")

        # Group bars by date and extract opening range volume for each day
        # IB returns timezone-NAIVE bars at 9:30 AM (ET market time)
        eastern_tz = pytz.timezone('US/Eastern')
        pacific_tz = pytz.timezone('US/Pacific')
        volumes_by_date = {}

        for idx, row in bars.iterrows():
            bar_time = row['date']

            # IB returns naive timestamps - localize as ET first, then convert to PST
            if bar_time.tzinfo is None:
                bar_time = eastern_tz.localize(bar_time)  # 9:30 AM → 9:30 AM ET
            bar_time = bar_time.astimezone(pacific_tz)  # 9:30 AM ET → 6:30 AM PST

            # Extract date
            bar_date = bar_time.date()

            # Market opens at 6:30 AM PST (9:30 AM ET)
            market_open_pst = pacific_tz.localize(
                datetime.combine(bar_date, time(hour=6, minute=30))
            )

            # Check if this is the opening range bar (first bar at or after 6:30 AM PST)
            if bar_time >= market_open_pst and bar_time < market_open_pst + timedelta(minutes=5):
                # This is the opening 5-minute bar
                volume = int(row['volume'])

                # Only store if we don't already have this date (take first occurrence)
                if bar_date not in volumes_by_date:
                    volumes_by_date[bar_date] = volume
                    logger.debug(
                        f"{symbol} opening range volume on {bar_date}: {volume:,} "
                        f"(bar time: {bar_time.strftime('%Y-%m-%d %H:%M:%S %Z')})"
                    )

        if not volumes_by_date:
            raise RuntimeError(
                f"Could not extract opening range volumes for {symbol} - "
                f"no bars found at market open (6:30 AM PST) in {len(bars)} bars"
            )

        # Sort by date and extract volumes
        sorted_dates = sorted(volumes_by_date.keys(), reverse=True)  # Most recent first
        volumes = [volumes_by_date[date] for date in sorted_dates[:lookback_days]]

        if len(volumes) < lookback_days:
            raise RuntimeError(
                f"Insufficient trading history for {symbol}: "
                f"found {len(volumes)} days, need {lookback_days} days"
            )

        logger.debug(
            f"Extracted {len(volumes)} opening range volumes for {symbol} "
            f"(requested {lookback_days} days)"
        )

        return volumes

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
