from src.core.command import Command
from src.core.constants import *
from src.stocks.services.volume_analysis_service import VolumeAnalysisService
from src import logger
import pytz
from datetime import datetime
import numpy as np
from prettytable import PrettyTable

class VolumeAnalysisCommand(Command):
    """
    DEPRECATED: Z-Score Volume Analysis Command

    This command is NOT part of the Academic ORB Strategy (ssrn-4729284.pdf).
    The academic paper uses ONLY Relative Volume (RV >= 100% + Top 20) filtering,
    with NO Z-score validation on breakout bars.

    Kept for historical reference and manual analysis only.
    This command is disabled in stocks_trade_manager.py.

    Usage: /va AAPL (if manually enabled)
    """

    def execute(self, event):
        """
        Execute volume analysis for specified symbol
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        # Extract symbol from event
        symbol = event.get(FIELD_DATA)
        if not symbol:
            self.state_manager.sendTelegramMessage("❌ Usage: /va SYMBOL")
            return

        symbol = symbol.upper().strip()
        logger.info(f"Executing volume analysis for {symbol}")

        try:
            # Get configuration
            timeframe_minutes = self.state_manager.get_config_value(CONFIG_ORB_TIMEFRAME)
            if timeframe_minutes is None:
                raise ValueError("CONFIG_ORB_TIMEFRAME not configured")

            lookback_days = self.state_manager.get_config_value(CONFIG_ORB_VOLUME_LOOKBACK_DAYS)
            if lookback_days is None or lookback_days <= 0:
                raise ValueError("CONFIG_ORB_VOLUME_LOOKBACK_DAYS is REQUIRED and must be positive")

            zscore_threshold = self.state_manager.get_config_value(CONFIG_ORB_VOLUME_ZSCORE_THRESHOLD)
            if zscore_threshold is None or zscore_threshold <= 0:
                raise ValueError("CONFIG_ORB_VOLUME_ZSCORE_THRESHOLD is REQUIRED and must be positive")

            # Fetch historical bars using extended method for multi-day data
            ib_client = self.application_context.client
            bars_df = ib_client.get_stock_bars_extended(
                symbol=symbol,
                duration_days=lookback_days,
                bar_size=f"{timeframe_minutes} mins"
            )

            # Get the most recent bar
            latest_bar = bars_df.iloc[-1]

            # Initialize volume service
            volume_service = VolumeAnalysisService(self.application_context)

            # Calculate Z-Score
            volume_zscore = volume_service.calculate_volume_zscore(
                bars_df=bars_df,
                current_bar=latest_bar,
                lookback_days=lookback_days,
                timeframe_minutes=timeframe_minutes
            )

            # Get same-time historical volumes for display
            same_time_data = self._get_same_time_volumes(bars_df, latest_bar)

            # Format and send analysis
            self._send_analysis_report(
                symbol=symbol,
                latest_bar=latest_bar,
                same_time_data=same_time_data,
                volume_zscore=volume_zscore,
                zscore_threshold=zscore_threshold,
                timeframe_minutes=timeframe_minutes
            )

        except Exception as e:
            logger.error(f"Volume analysis failed for {symbol}: {str(e)}")
            self.state_manager.sendTelegramMessage(f"❌ Volume analysis failed: {str(e)}")

    def _get_same_time_volumes(self, bars_df, current_bar):
        """
        Get historical volumes at the same time of day with timestamps
        """
        est_tz = pytz.timezone('US/Eastern')
        pst_tz = pytz.timezone('US/Pacific')

        current_bar_time_est = current_bar['date']
        if current_bar_time_est.tzinfo is None:
            current_bar_time_est = est_tz.localize(current_bar_time_est)

        current_bar_time_pst = current_bar_time_est.astimezone(pst_tz)
        current_time_of_day = current_bar_time_pst.time()

        historical_data = []

        for idx, row in bars_df.iterrows():
            bar_time_est = row['date']
            if bar_time_est.tzinfo is None:
                bar_time_est = est_tz.localize(bar_time_est)

            bar_time_pst = bar_time_est.astimezone(pst_tz)

            # Same time of day but not current bar
            if (bar_time_pst.time() == current_time_of_day and
                bar_time_pst.date() != current_bar_time_pst.date()):
                historical_data.append({
                    'date': bar_time_pst.strftime('%m/%d'),
                    'time': bar_time_pst.strftime('%H:%M'),
                    'volume': int(row['volume']),
                    'full_timestamp': bar_time_pst
                })

        # Sort by date and return all points
        return sorted(historical_data, key=lambda x: x['full_timestamp'])

    def _send_analysis_report(self, symbol, latest_bar, same_time_data,
                             volume_zscore, zscore_threshold, timeframe_minutes):
        """
        Format and send the analysis report using PrettyTable
        """
        # Get time info
        latest_time = latest_bar['date']
        if latest_time.tzinfo is None:
            est_tz = pytz.timezone('US/Eastern')
            latest_time = est_tz.localize(latest_time)

        pst_tz = pytz.timezone('US/Pacific')
        latest_time_pst = latest_time.astimezone(pst_tz)

        # Calculate statistics
        volumes = [d['volume'] for d in same_time_data]
        if volumes:
            mean_vol = np.mean(volumes)
            std_vol = np.std(volumes, ddof=1) if len(volumes) > 1 else 0
        else:
            mean_vol = 0
            std_vol = 0

        # Create PrettyTable
        table = PrettyTable(['Date', 'Time', 'Volume'])
        table.align['Date'] = 'c'
        table.align['Time'] = 'c'
        table.align['Volume'] = 'r'

        # Add historical data rows
        for data in same_time_data:
            table.add_row([
                data['date'],
                data['time'],
                f"{data['volume']:,}"
            ])

        # Build message
        msg = f"📊 <b>Volume Analysis: {symbol}</b>\n"
        msg += f"Current Bar: {latest_time_pst.strftime('%m/%d %H:%M')} PST ({timeframe_minutes}min)\n"
        msg += f"Current Volume: {int(latest_bar['volume']):,}\n\n"
        msg += f"<b>Historical Same-Time Volumes:</b>\n"
        msg += f"<pre>{table}</pre>\n"

        # Add statistics outside the table
        msg += f"Mean: {int(mean_vol):,}\n"
        msg += f"StdDev: {int(std_vol):,}\n"
        msg += f"Points: {len(same_time_data)}\n\n"

        # Analysis section
        msg += f"<b>Analysis:</b>\n"
        msg += f"Z-Score: <b>{volume_zscore:.2f}σ</b>\n"
        msg += f"Threshold: {zscore_threshold:.1f}σ\n"
        msg += f"Formula: ({int(latest_bar['volume']):,} - {int(mean_vol):,}) / {int(std_vol):,}\n\n"

        # Result
        if volume_zscore >= zscore_threshold:
            msg += "✅ <b>PASS</b> - Volume confirmed for breakout"
        else:
            msg += "❌ <b>FAIL</b> - Insufficient volume for breakout"

        # Send with HTML parsing (consistent with other commands)
        self.state_manager.sendTelegramMessage(msg)