"""
Volatility Service - Real-time volatility analysis for options strategy selection
Based on concepts from Natenberg's Option Volatility and Pricing
"""

from src import logger
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class VolatilityService:
    """Service for real-time volatility analysis and options data"""

    def __init__(self, application_context):
        """
        Initialize volatility service

        Args:
            application_context: Application context with client

        Raises:
            ValueError: If application_context is None
        """
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.client = application_context.client
        self.application_context = application_context

    def get_historical_prices(self, symbol: str, duration: str, bar_size: str) -> pd.DataFrame:
        """
        Get historical OHLC bars using IB native format

        Args:
            symbol: Stock symbol (required)
            duration: IB duration string (required) - e.g., "252 D", "390 S", "1 M"
            bar_size: IB bar size (required) - e.g., "1 day", "30 mins", "1 hour"

        Returns:
            DataFrame with columns: date, open, high, low, close, volume

        Raises:
            ValueError: If any parameter is None or invalid
            RuntimeError: If no data received from IB
            TimeoutError: If request times out
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if not duration:
            raise ValueError("duration is REQUIRED")
        if not bar_size:
            raise ValueError("bar_size is REQUIRED")

        logger.info(f"Fetching historical prices for {symbol}: duration={duration}, bar_size={bar_size}")

        # Create stock contract
        contract = self.client.get_stock_contract(symbol)

        # Get historical data using IB native parameters (no conversion)
        bars = self.client.get_historic_data(
            contract=contract,
            history_duration=duration,
            history_bar_size=bar_size,
            timeout=10,
            whatToShow="TRADES"
        )

        if bars is None:
            raise TimeoutError(f"Timeout getting historical data for {symbol}")
        if bars.empty:
            raise RuntimeError(f"No historical data received for {symbol}")

        logger.info(f"Retrieved {len(bars)} bars for {symbol}")
        return bars

    def calculate_historical_volatility(
        self,
        prices: pd.Series,
        periods: List[int] = [10, 20, 30, 60]
    ) -> Dict[str, float]:
        """
        Calculate annualized historical volatility using log returns (Natenberg formula)

        Formula: HV = std(ln(P[t]/P[t-1])) * sqrt(252)

        Args:
            prices: Series of closing prices (required)
            periods: List of lookback periods in days (default: [10, 20, 30, 60])

        Returns:
            Dict mapping period to annualized volatility (e.g., {"HV_20": 0.25})

        Raises:
            ValueError: If prices is None or empty
        """
        if prices is None or len(prices) == 0:
            raise ValueError("prices is REQUIRED and cannot be empty")
        if not periods:
            raise ValueError("periods is REQUIRED")

        logger.info(f"Calculating historical volatility for {len(periods)} periods")

        # Calculate log returns
        log_returns = np.log(prices / prices.shift(1))

        results = {}
        for period in periods:
            if len(prices) < period:
                logger.warning(f"Insufficient data for {period}-day HV (need {period}, have {len(prices)})")
                continue

            # Calculate rolling standard deviation
            rolling_std = log_returns.rolling(window=period).std()

            # Annualize (252 trading days per year)
            annualized_vol = rolling_std * np.sqrt(252)

            # Get most recent value
            current_hv = annualized_vol.iloc[-1]

            if not np.isnan(current_hv):
                results[f"HV_{period}"] = float(current_hv)
                logger.debug(f"HV_{period}: {current_hv:.2%}")

        if not results:
            raise RuntimeError("Could not calculate any HV values - insufficient data")

        return results

    def get_current_atm_iv(self, symbol: str) -> Dict[str, float]:
        """
        Get current at-the-money (ATM) implied volatility

        Finds the strike closest to current stock price and returns average IV of call/put

        Args:
            symbol: Stock symbol (required)

        Returns:
            Dict with:
                - atm_iv: Average of call/put IV
                - atm_iv_call: Call IV
                - atm_iv_put: Put IV
                - atm_strike: Strike used
                - current_price: Current stock price
                - expiration: Expiration used (closest to 30 days)

        Raises:
            ValueError: If symbol is None
            RuntimeError: If unable to get options data
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        logger.info(f"Getting ATM implied volatility for {symbol}")

        # Get current stock price
        current_price = self.client.get_stock_price(symbol)
        logger.info(f"Current price for {symbol}: ${current_price:.2f}")

        # Get options chain
        chain_data = self.client.get_options_chain(symbol)
        if not chain_data:
            raise RuntimeError(f"Could not get options chain for {symbol}")

        expirations = sorted(chain_data['expirations'])
        strikes = sorted(chain_data['strikes'])

        if not expirations or not strikes:
            raise RuntimeError(f"No expirations or strikes found for {symbol}")

        logger.info(f"Found {len(expirations)} expirations and {len(strikes)} strikes")

        # Find expiration closest to 30 days out
        target_date = datetime.now().date() + timedelta(days=30)
        closest_expiration = min(
            expirations,
            key=lambda x: abs((datetime.strptime(x, '%Y%m%d').date() - target_date).days)
        )
        logger.info(f"Using expiration: {closest_expiration}")

        # Get available strikes for this specific expiration
        expiration_strikes = self.client.get_strikes_for_expiration(symbol, closest_expiration)
        if not expiration_strikes:
            raise RuntimeError(f"No strikes found for {symbol} expiration {closest_expiration}")

        # Find ATM strike (closest to current price) from available strikes for this expiration
        atm_strike = min(expiration_strikes, key=lambda x: abs(x - current_price))
        logger.info(f"ATM strike: {atm_strike} (from {len(expiration_strikes)} available strikes)")

        # Get Greeks for call and put at ATM strike
        call_greeks = self.client.get_option_greeks(
            symbol=symbol,
            expiry=closest_expiration,
            strike=atm_strike,
            right="C"
        )

        put_greeks = self.client.get_option_greeks(
            symbol=symbol,
            expiry=closest_expiration,
            strike=atm_strike,
            right="P"
        )

        # Extract IV values
        call_iv = call_greeks.get('iv') if call_greeks else None
        put_iv = put_greeks.get('iv') if put_greeks else None

        if call_iv is None and put_iv is None:
            raise RuntimeError(f"Could not get IV for {symbol} at strike {atm_strike}")

        # Calculate average (handle case where one might be None)
        if call_iv is not None and put_iv is not None:
            atm_iv = (call_iv + put_iv) / 2
        elif call_iv is not None:
            atm_iv = call_iv
        else:
            atm_iv = put_iv

        logger.info(f"ATM IV for {symbol}: {atm_iv:.2%} (call={call_iv}, put={put_iv})")

        return {
            'atm_iv': float(atm_iv),
            'atm_iv_call': float(call_iv) if call_iv is not None else None,
            'atm_iv_put': float(put_iv) if put_iv is not None else None,
            'atm_strike': float(atm_strike),
            'current_price': float(current_price),
            'expiration': closest_expiration
        }

    def get_volatility_term_structure(
        self,
        symbol: str,
        target_days: List[int] = [30, 60, 90]
    ) -> Dict:
        """
        Get implied volatility term structure across multiple expirations

        Args:
            symbol: Stock symbol (required)
            target_days: Target days to expiration (default: [30, 60, 90])

        Returns:
            Dict with:
                - term_structure: List of {days_to_expiry, iv, expiration}
                - slope: Term structure slope (back_iv - front_iv) / front_iv
                - front_iv: Shortest expiration IV
                - back_iv: Longest expiration IV

        Raises:
            ValueError: If symbol is None
            RuntimeError: If unable to get options data
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if not target_days:
            raise ValueError("target_days is REQUIRED")

        logger.info(f"Getting volatility term structure for {symbol}")

        # Get current stock price
        current_price = self.client.get_stock_price(symbol)

        # Get options chain
        chain_data = self.client.get_options_chain(symbol)
        if not chain_data:
            raise RuntimeError(f"Could not get options chain for {symbol}")

        expirations = sorted(chain_data['expirations'])
        strikes = sorted(chain_data['strikes'])

        if not expirations or not strikes:
            raise RuntimeError(f"No expirations or strikes found for {symbol}")

        term_structure = []
        today = datetime.now().date()

        for target in target_days:
            # Find expiration closest to target days
            target_date = today + timedelta(days=target)
            closest_exp = min(
                expirations,
                key=lambda x: abs((datetime.strptime(x, '%Y%m%d').date() - target_date).days)
            )

            # Calculate actual days to expiry
            exp_date = datetime.strptime(closest_exp, '%Y%m%d').date()
            days_to_expiry = (exp_date - today).days

            # Get available strikes for this specific expiration
            expiration_strikes = self.client.get_strikes_for_expiration(symbol, closest_exp)
            if not expiration_strikes:
                logger.warning(f"No strikes found for {symbol} expiration {closest_exp}, skipping")
                continue

            # Find ATM strike for this expiration
            atm_strike = min(expiration_strikes, key=lambda x: abs(x - current_price))

            # Get IV for this expiration (use call IV)
            greeks = self.client.get_option_greeks(
                symbol=symbol,
                expiry=closest_exp,
                strike=atm_strike,
                right="C"
            )

            if greeks and greeks.get('iv'):
                iv = greeks['iv']
                term_structure.append({
                    'target_days': target,
                    'days_to_expiry': days_to_expiry,
                    'iv': float(iv),
                    'expiration': closest_exp
                })
                logger.info(f"Term structure point: {days_to_expiry} days (strike {atm_strike}) -> IV {iv:.2%}")

        if not term_structure:
            raise RuntimeError(f"Could not build term structure for {symbol}")

        # Sort by days to expiry
        term_structure.sort(key=lambda x: x['days_to_expiry'])

        # Calculate slope
        front_iv = term_structure[0]['iv']
        back_iv = term_structure[-1]['iv']
        slope = (back_iv - front_iv) / front_iv if front_iv > 0 else 0

        logger.info(f"Term structure slope: {slope:.2%}")

        return {
            'symbol': symbol,
            'term_structure': term_structure,
            'slope': float(slope),
            'front_iv': float(front_iv),
            'back_iv': float(back_iv),
            'atm_strike': float(atm_strike)
        }

    def analyze_complete_volatility(self, symbol: str) -> Dict:
        """
        Perform complete real-time volatility analysis

        Combines:
        - Current ATM implied volatility
        - Historical volatility (10, 20, 30, 60 day)
        - IV/HV ratio
        - Volatility term structure

        Args:
            symbol: Stock symbol (required)

        Returns:
            Dict with complete volatility analysis ready for strategy selection

        Raises:
            ValueError: If symbol is None
            RuntimeError: If analysis fails
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        logger.info(f"Performing complete volatility analysis for {symbol}")

        try:
            # 1. Get historical prices (252 days for robust HV calculation)
            prices_df = self.get_historical_prices(symbol, duration="252 D", bar_size="1 day")
            prices = prices_df['close']

            # 2. Calculate historical volatility
            hv_data = self.calculate_historical_volatility(prices, periods=[10, 20, 30, 60])

            # 3. Get current ATM IV
            iv_data = self.get_current_atm_iv(symbol)

            # 4. Get term structure
            term_structure_data = self.get_volatility_term_structure(symbol, target_days=[30, 60, 90])

            # 5. Calculate IV/HV ratio (using 20-day HV as baseline)
            baseline_hv = hv_data.get('HV_20', hv_data.get('HV_30', 0))
            current_iv = iv_data['atm_iv']
            iv_hv_ratio = current_iv / baseline_hv if baseline_hv > 0 else 1.0

            # Compile comprehensive analysis
            analysis = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'current_price': iv_data['current_price'],

                # Implied Volatility
                'implied_volatility': {
                    'atm_iv': current_iv,
                    'atm_iv_call': iv_data['atm_iv_call'],
                    'atm_iv_put': iv_data['atm_iv_put'],
                    'atm_strike': iv_data['atm_strike'],
                    'expiration': iv_data['expiration']
                },

                # Historical Volatility
                'historical_volatility': hv_data,

                # Ratios
                'iv_hv_ratio': float(iv_hv_ratio),

                # Term Structure
                'term_structure': {
                    'slope': term_structure_data['slope'],
                    'front_iv': term_structure_data['front_iv'],
                    'back_iv': term_structure_data['back_iv'],
                    'structure': term_structure_data['term_structure']
                },

                # Trading Signal (basic)
                'signal': self._generate_basic_signal(current_iv, baseline_hv, iv_hv_ratio)
            }

            logger.info(f"Complete volatility analysis for {symbol}:")
            logger.info(f"  Current IV: {current_iv:.2%}")
            logger.info(f"  HV (20-day): {baseline_hv:.2%}")
            logger.info(f"  IV/HV Ratio: {iv_hv_ratio:.2f}")
            logger.info(f"  Term Structure Slope: {term_structure_data['slope']:.2%}")

            return analysis

        except Exception as e:
            logger.error(f"Error in complete volatility analysis for {symbol}: {e}")
            raise RuntimeError(f"Volatility analysis failed for {symbol}: {str(e)}")

    def _generate_basic_signal(self, current_iv: float, baseline_hv: float, iv_hv_ratio: float) -> str:
        """
        Generate basic trading signal from volatility analysis

        Args:
            current_iv: Current implied volatility
            baseline_hv: Baseline historical volatility
            iv_hv_ratio: IV/HV ratio

        Returns:
            Signal string: "BUY_VOLATILITY", "SELL_VOLATILITY", or "NEUTRAL"
        """
        if iv_hv_ratio < 0.85:
            return "BUY_VOLATILITY - Options appear underpriced relative to historical volatility"
        elif iv_hv_ratio > 1.25:
            return "SELL_VOLATILITY - Options appear overpriced relative to historical volatility"
        else:
            return "NEUTRAL - Use spread strategies or wait for better volatility opportunities"
