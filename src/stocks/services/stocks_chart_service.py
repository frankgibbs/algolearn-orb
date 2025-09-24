"""
Chart generation service for stock data visualization
"""

import mplfinance as mpf
from io import BytesIO
import matplotlib
matplotlib.use('agg')
import pandas as pd
from datetime import datetime
from src import logger

class StocksChartService:
    """Service for generating stock price charts"""

    def __init__(self):
        """Initialize chart service"""
        pass

    def generate_candlestick_chart(self, df_data, symbol, opening_range=None):
        """
        Generate candlestick chart compatible with Telegram

        Args:
            df_data: DataFrame with OHLC data
            symbol: Stock symbol for title
            opening_range: Optional OpeningRange object for support/resistance lines

        Returns:
            BytesIO buffer containing chart image

        Raises:
            ValueError: If df_data is None or empty
            RuntimeError: If chart generation fails
        """
        if df_data is None or df_data.empty:
            raise ValueError("df_data is REQUIRED and cannot be empty")

        if not symbol:
            raise ValueError("symbol is REQUIRED")

        logger.info(f"Generating candlestick chart for {symbol}")

        try:
            buf = BytesIO()

            # Ensure DataFrame has proper datetime index
            if not isinstance(df_data.index, pd.DatetimeIndex):
                if 'datetime' in df_data.columns:
                    df_data = df_data.set_index('datetime')
                    df_data.index = pd.to_datetime(df_data.index)
                elif 'date' in df_data.columns:
                    df_data = df_data.set_index('date')
                    df_data.index = pd.to_datetime(df_data.index)
                else:
                    df_data.index = pd.to_datetime(df_data.index)

            # Ensure proper column names for mplfinance
            df_plot = df_data.copy()

            # Map common column names to mplfinance expected format
            column_mapping = {
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume',
                'Open': 'Open',
                'High': 'High',
                'Low': 'Low',
                'Close': 'Close',
                'Volume': 'Volume'
            }

            # Rename columns if they exist
            existing_columns = {col: column_mapping.get(col, col) for col in df_plot.columns if col in column_mapping}
            df_plot = df_plot.rename(columns=existing_columns)

            # Ensure we have at least OHLC data
            required_columns = ['Open', 'High', 'Low', 'Close']
            missing_columns = [col for col in required_columns if col not in df_plot.columns]

            if missing_columns:
                raise ValueError(f"Missing required columns: {missing_columns}")

            # Create chart style
            mc = mpf.make_marketcolors(
                up='g', down='r',
                edge='inherit',
                wick={'up':'green', 'down':'red'},
                volume='in'
            )

            style = mpf.make_mpf_style(
                marketcolors=mc,
                gridstyle='-',
                y_on_right=True
            )

            # Determine if we have volume data
            include_volume = 'Volume' in df_plot.columns and not df_plot['Volume'].isna().all()

            # Prepare horizontal lines for opening range
            plot_kwargs = {
                'type': 'candle',
                'style': style,
                'title': f'{symbol} - {datetime.now().strftime("%Y-%m-%d")}',
                'ylabel': 'Price ($)',
                'ylabel_lower': 'Volume' if include_volume else None,
                'volume': include_volume,
                'savefig': dict(
                    fname=buf,
                    dpi=100,
                    bbox_inches='tight',
                    facecolor='white'
                ),
                'returnfig': False,
                'scale_padding': {'left': 0.3, 'top': 0.8, 'right': 0.5, 'bottom': 0.5}
            }

            # Add opening range lines if available
            if opening_range is not None:
                plot_kwargs['hlines'] = dict(
                    hlines=[opening_range.range_low, opening_range.range_high],
                    colors=['green', 'red'],
                    linestyle='-.',
                    linewidths=1.5,
                    alpha=0.8
                )

            # Create the plot
            mpf.plot(df_plot, **plot_kwargs)

            buf.seek(0)
            logger.info(f"Successfully generated chart for {symbol}")
            return buf

        except Exception as e:
            logger.error(f"Error generating chart for {symbol}: {e}")
            raise RuntimeError(f"Failed to generate chart: {str(e)}")

    def generate_range_chart(self, df_data, symbol, opening_range=None):
        """
        Generate chart with opening range overlay

        Args:
            df_data: DataFrame with OHLC data
            symbol: Stock symbol
            opening_range: Optional opening range data to overlay

        Returns:
            BytesIO buffer containing chart image
        """
        if df_data is None or df_data.empty:
            raise ValueError("df_data is REQUIRED and cannot be empty")

        logger.info(f"Generating range chart for {symbol}")

        try:
            # Start with basic candlestick chart
            buf = self.generate_candlestick_chart(df_data, symbol)

            # If opening range provided, we could add horizontal lines
            # For now, return the basic chart
            # TODO: Add opening range overlay functionality if needed

            return buf

        except Exception as e:
            logger.error(f"Error generating range chart for {symbol}: {e}")
            raise RuntimeError(f"Failed to generate range chart: {str(e)}")