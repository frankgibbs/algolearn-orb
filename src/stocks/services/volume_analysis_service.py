from src import logger
import numpy as np
import pytz

class VolumeAnalysisService:
    """Service for volume analysis and statistical calculations"""

    def __init__(self, application_context):
        """
        Initialize volume analysis service

        Args:
            application_context: Application context with state manager
        """
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.state_manager = application_context.state_manager
        self.application_context = application_context

    def calculate_volume_zscore(self, bars_df, current_bar, lookback_days, timeframe_minutes):
        """
        Calculate Volume Z-Score comparing current bar to same time-of-day historical statistics.

        Z-Score = (Current Volume - Mean Volume) / Standard Deviation

        Args:
            bars_df: DataFrame with all historical bars
            current_bar: The bar to calculate Z-Score for
            lookback_days: Number of calendar days to look back
            timeframe_minutes: Bar size in minutes (for context)

        Returns:
            float: Z-Score (number of standard deviations from mean)
        """
        if bars_df is None or bars_df.empty:
            raise ValueError("bars_df is REQUIRED and cannot be empty")
        if current_bar is None:
            raise ValueError("current_bar is REQUIRED")
        if lookback_days is None or lookback_days <= 0:
            raise ValueError("lookback_days is REQUIRED and must be positive")
        if timeframe_minutes is None or timeframe_minutes <= 0:
            raise ValueError("timeframe_minutes is REQUIRED and must be positive")

        # Get same time-of-day volumes
        same_time_volumes = self._get_same_time_volumes(
            bars_df, current_bar, lookback_days, timeframe_minutes
        )

        # Need at least 5 historical points for meaningful statistics
        if len(same_time_volumes) < 5:
            logger.warning(f"Only {len(same_time_volumes)} historical points for Z-Score calculation")
            return 0.0  # Neutral Z-Score if insufficient data

        # Calculate statistics
        mean_volume = np.mean(same_time_volumes)
        std_volume = np.std(same_time_volumes, ddof=1)  # Sample standard deviation

        # Handle edge case of no variance
        if std_volume == 0:
            current_volume = current_bar['volume']
            logger.warning(f"Zero variance in historical volumes")
            # If current equals mean, z-score is 0; otherwise it's significant
            return 0.0 if current_volume == mean_volume else 10.0

        # Calculate Z-Score
        current_volume = current_bar['volume']
        z_score = (current_volume - mean_volume) / std_volume

        logger.debug(f"Volume Z-Score: Current={current_volume:,}, "
                    f"Mean={mean_volume:,.0f}, StdDev={std_volume:,.0f}, "
                    f"Z-Score={z_score:.2f}σ ({len(same_time_volumes)} points)")

        return round(z_score, 2)

    def _get_same_time_volumes(self, bars_df, current_bar, lookback_days, timeframe_minutes):
        """
        Extract volumes from bars at the same time of day as current_bar

        Returns:
            list: Volumes at the same time of day
        """
        # Get current bar's time in EST (bars from IB are in EST)
        current_bar_time_est = current_bar['date']

        # Convert to PST for consistent comparison (container runs in PST)
        est_tz = pytz.timezone('US/Eastern')
        pst_tz = pytz.timezone('US/Pacific')

        # Ensure timezone awareness
        if current_bar_time_est.tzinfo is None:
            current_bar_time_est = est_tz.localize(current_bar_time_est)

        current_bar_time_pst = current_bar_time_est.astimezone(pst_tz)
        current_time_of_day = current_bar_time_pst.time()

        # Collect all volumes at the same time of day (excluding current bar)
        same_time_volumes = []

        for idx, row in bars_df.iterrows():
            bar_time_est = row['date']
            if bar_time_est.tzinfo is None:
                bar_time_est = est_tz.localize(bar_time_est)

            bar_time_pst = bar_time_est.astimezone(pst_tz)

            # Check if same time of day and not the current bar
            if (bar_time_pst.time() == current_time_of_day and
                bar_time_pst.date() != current_bar_time_pst.date()):
                same_time_volumes.append(row['volume'])

        return same_time_volumes

    def is_volume_significant(self, z_score, threshold):
        """
        Check if volume Z-Score meets significance threshold

        Args:
            z_score: Calculated Z-Score
            threshold: Threshold for significance

        Returns:
            bool: True if volume is significant
        """
        if z_score is None:
            raise ValueError("z_score is REQUIRED")
        if threshold is None or threshold <= 0:
            raise ValueError("threshold is REQUIRED and must be positive")

        return z_score >= threshold