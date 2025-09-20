from datetime import datetime, timedelta
from src import logger
from src.core.constants import FIELD_NEXT_ORDER_ID, FIELD_TYPE, EVENT_TYPE_CREATE_NEW_ORDER, FIELD_ORDER, FIELD_CONTRACT,FIELD_STOP_PRICE, FIELD_ORDER_ID, FIELD_VALUE_ESTIMATE, LONG, SHORT, NONE, FOREX_PAIRS
import base64
import io
import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib.pyplot as plt
import requests
import re
import os
import talib
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def load_prompt(prompt_name):
    """Load a prompt from the prompts directory"""
    prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', f'{prompt_name}.txt')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error(f"Prompt file not found: {prompt_path}")
        return None
    except Exception as e:
        logger.error(f"Error loading prompt {prompt_name}: {e}")
        return None

def calculate_profit(lot_size, entry_price, close_price, trade_direction):
    
    logger.info(f"calculate_profit called with: lot_size={lot_size} ({type(lot_size)}), entry_price={entry_price} ({type(entry_price)}), close_price={close_price} ({type(close_price)}), trade_direction={trade_direction} ({type(trade_direction)})")
    
    if trade_direction not in ['BUY', 'SELL']:
        raise ValueError("Trade direction must be 'BUY' or 'SELL'")
    
    if trade_direction == 'BUY':
        profit = (close_price - entry_price) * lot_size
    else:  # trade_direction == 'SELL'
        profit = (entry_price - close_price) * lot_size

    logger.info(f"calculate_profit result: {profit}")
    return profit
        
def calculate_roi(lot_size, margin_percentage, entry_price, close_price, trade_direction):
    
    logger.info(f"calculate_roi called with: lot_size={lot_size} ({type(lot_size)}), margin_percentage={margin_percentage} ({type(margin_percentage)}), entry_price={entry_price} ({type(entry_price)}), close_price={close_price} ({type(close_price)}), trade_direction={trade_direction} ({type(trade_direction)})")
    
    if trade_direction not in ['BUY', 'SELL']:
        raise ValueError("Trade direction must be 'BUY' or 'SELL'")
    
    margin = margin_percentage * lot_size

    if trade_direction == 'BUY':
        pnl = (close_price - entry_price) * lot_size
    else:  # trade_direction == 'SELL'
        pnl = (entry_price - close_price) * lot_size
    
    roi = pnl / margin

    logger.info(f"calculate_roi result: {roi}")
    return roi

def calculate_pip_based_roi(entry_price, close_price, initial_stop_price, trade_direction, pip_size):
    """
    Calculate risk-adjusted ROI using pip-based approach.
    
    Args:
        entry_price: Entry price of the trade
        close_price: Close price of the trade  
        initial_stop_price: Original stop loss price
        trade_direction: 'BUY' or 'SELL'
        pip_size: Pip size for the currency pair
        
    Returns:
        float: ROI as ratio (pip_profit / pip_risk)
    """
    logger.info(f"calculate_pip_based_roi called with: entry={entry_price}, close={close_price}, stop={initial_stop_price}, direction={trade_direction}, pip_size={pip_size}")
    
    if trade_direction not in ['BUY', 'SELL']:
        raise ValueError("Trade direction must be 'BUY' or 'SELL'")
    
    # Calculate profit in pips
    if trade_direction == 'BUY':
        pip_profit = (close_price - entry_price) / pip_size
    else:  # SELL
        pip_profit = (entry_price - close_price) / pip_size
    
    # Calculate risk in pips (distance to initial stop)
    pip_risk = abs(entry_price - initial_stop_price) / pip_size
    
    # Calculate risk-adjusted ROI
    roi = pip_profit / pip_risk if pip_risk > 0 else 0
    
    logger.info(f"Pip-based ROI: {pip_profit:.1f} pips / {pip_risk:.1f} pips = {roi:.4f} ({roi*100:.2f}%)")
    
    return roi

def calculate_unrealized_pnl(pip_size, opening_price, current_price, trade_direction, decimal_places):

    if trade_direction not in ['BUY', 'SELL']:
        raise ValueError("Trade direction must be 'BUY' or 'SELL'")
    
    if trade_direction == 'BUY':
        pnl = (current_price - opening_price) / pip_size
    else:  # trade_direction == 'SELL'
        pnl = (opening_price - current_price) / pip_size
    
    return round(pnl,decimal_places)

def calculate_usd_pnl(lot_size, entry_price, close_price, trade_direction, trading_pair, exchange_rate_cache):
    """
    Calculate PnL and convert to USD using exchange rate cache
    
    Args:
        lot_size: Size of the trade
        entry_price: Entry price
        close_price: Close price
        trade_direction: 'BUY' or 'SELL'
        trading_pair: Trading pair (e.g., 'USD.CAD', 'USD.JPY')
        exchange_rate_cache: Dictionary containing exchange rates
        
    Returns:
        PnL in USD, or in original currency if conversion not possible
    """
    logger.info(f"calculate_usd_pnl called with: lot_size={lot_size}, entry_price={entry_price}, close_price={close_price}, trade_direction={trade_direction}, trading_pair={trading_pair}")
    
    if trade_direction not in ['BUY', 'SELL']:
        raise ValueError("Trade direction must be 'BUY' or 'SELL'")
    
    # Calculate profit in quote currency
    if trade_direction == 'BUY':
        profit = (close_price - entry_price) * lot_size
    else:  # trade_direction == 'SELL'
        profit = (entry_price - close_price) * lot_size
    
    # Extract quote currency from trading pair
    quote_currency = trading_pair.split('.')[1]
    logger.info(f"Profit in {quote_currency}: {profit:.5f}")
    
    # If profit is already in USD, return as-is
    if quote_currency == 'USD':
        logger.info(f"Profit already in USD: ${profit:.2f}")
        return profit
    
    # Convert to USD using exchange rate cache with trading pair as key
    if trading_pair in exchange_rate_cache:
        usd_rate = exchange_rate_cache[trading_pair]
        
        # Extract base currency from trading pair
        base_currency = trading_pair.split('.')[0]
        
        # For USD-based pairs (e.g., USD.JPY), the rate is how many quote units per USD
        # So to convert quote currency profit to USD, we need to divide by the rate
        if base_currency == 'USD':
            usd_pnl = profit / usd_rate
            logger.info(f"Converted {profit} {quote_currency} to ${usd_pnl:.2f} USD by dividing by rate {usd_rate:.5f} for USD-based pair {trading_pair}")
        else:
            # For other pairs, multiply by the rate (which should be quote_to_USD rate)
            usd_pnl = profit * usd_rate
            logger.info(f"Converted {profit} {quote_currency} to ${usd_pnl:.2f} USD by multiplying by rate {usd_rate:.5f} for {trading_pair}")
        
        return usd_pnl
    else:
        error_msg = f"No USD conversion rate found for {trading_pair} in cache. Available rates: {list(exchange_rate_cache.keys())}"
        logger.error(error_msg)
        raise ValueError(error_msg)

def closest_expiration_date(expiration_dates, dte):
    # Convert the number of days to a timedelta object
    
    # Get today's date
    today = datetime.today().date()
    
    # Convert expiration dates to datetime objects
    expiration_dates = [datetime.strptime(str(date), '%Y%m%d').date() for date in expiration_dates]
    
    # Initialize variables to store the closest expiration date and its difference in days
    closest_date = None
    min_difference = float('inf')
    
    # Iterate through each expiration date and find the closest one to the target DTE
    for expiration_date in expiration_dates:
        # Calculate the difference in days between the expiration date and the target DTE
        difference = abs((expiration_date - today).days - dte)
        
        # Update the closest expiration date if a closer one is found
        if difference < min_difference:
            closest_date = expiration_date
            min_difference = difference
    
    
    closest_date_str = closest_date.strftime('%Y%m%d')
    return closest_date_str

def convert_balance_to_usd(currency, balance, exchange_rates):
    """
    Convert any currency balance to USD using exchange rate cache.
    
    Args:
        currency: Currency code (e.g., 'EUR', 'GBP', 'USD')
        balance: Amount in the currency
        exchange_rates: Exchange rate cache from state manager
        
    Returns:
        USD equivalent or None if conversion not possible
    """
    if currency == 'USD':
        return balance
    
    if not exchange_rates:
        return None
    
    # Try direct conversion first
    pair = f"{currency}.USD"
    if pair in exchange_rates:
        return balance * exchange_rates[pair]
    
    pair = f"USD.{currency}"
    if pair in exchange_rates:
        return balance / exchange_rates[pair]
    
    # Search all pairs containing this currency
    for pair_key, rate in exchange_rates.items():
        if '.' not in pair_key:
            continue
        base, quote = pair_key.split('.')
        
        # If this currency is involved in the pair
        if currency == quote and base == 'USD':
            return balance / rate
        elif currency == base and quote == 'USD':
            return balance * rate
    
    return None

def generate_candlestick_chart (df_data, contract, title: str = '15 Minute Chart'):
    """Generate a candlestick chart using mplfinance and return base64 encoded image"""
    # Create a figure and save it to a bytes buffer
    buf = io.BytesIO()
    
    symbol = contract.symbol
    currency = contract.currency
    pair = f"{symbol}.{currency}"

    chart_title = f"{pair} - {title}\nIndicators: RSI(14), MACD(12-blue,26-red), ATR(14-orange), Bollinger Bands(20,2-blue)"

    tmp = df_data.copy()
    tmp = tmp.set_index('date')
    tmp.index = pd.to_datetime(tmp.index)

    # Calculate RSI (14 period)
    delta = tmp['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    tmp['rsi'] = 100 - (100 / (1 + rs))
    
    # Calculate MACD (12, 26, 9)
    exp1 = tmp['close'].ewm(span=12, adjust=False).mean()
    exp2 = tmp['close'].ewm(span=26, adjust=False).mean()
    tmp['macd'] = exp1 - exp2
    tmp['signal'] = tmp['macd'].ewm(span=9, adjust=False).mean()
    tmp['macd_hist'] = tmp['macd'] - tmp['signal']
    
    # Calculate ATR (14 period)
    high_low = tmp['high'] - tmp['low']
    high_close = np.abs(tmp['high'] - tmp['close'].shift())
    low_close = np.abs(tmp['low'] - tmp['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    tmp['atr'] = true_range.rolling(14).mean()
    
    # Calculate Bollinger Bands (20 period, 2 standard deviations)
    period = 20
    std_dev = 2
    tmp['bb_middle'] = tmp['close'].rolling(window=period).mean()
    rolling_std = tmp['close'].rolling(window=period).std()
    tmp['bb_upper'] = tmp['bb_middle'] + (rolling_std * std_dev)
    tmp['bb_lower'] = tmp['bb_middle'] - (rolling_std * std_dev)
    tmp['bb_width'] = (tmp['bb_upper'] - tmp['bb_lower']) / tmp['bb_middle']  # Normalized BB width
    tmp['bb_pct'] = (tmp['close'] - tmp['bb_lower']) / (tmp['bb_upper'] - tmp['bb_lower'])  # Position within bands (0-1)
    
    # Drop any rows with NA values
    tmp = tmp.dropna()
    tmp = tmp.tail(50)
    
    # Calculate y-axis limits with extra margin to prevent cutting off Bollinger Bands
    price_min = tmp['bb_lower'].min()
    price_max = tmp['bb_upper'].max()
    price_range = price_max - price_min
    y_margin = price_range * 0.1  # Add 10% margin
    
    # Create a list of addplots for all indicators
    apds = []
    
    # Add RSI to panel 1
    apds.append(mpf.make_addplot(tmp.rsi, type='line', panel=1, color='black', ylabel='RSI (14)', width=1.5))
    
    # Add RSI reference lines at 30, 50, 70
    apds.append(mpf.make_addplot([30]*len(tmp), type='line', panel=1, color='gray', linestyle='--', width=0.5, alpha=0.3))
    apds.append(mpf.make_addplot([50]*len(tmp), type='line', panel=1, color='gray', linestyle='-', width=0.5, alpha=0.3))
    apds.append(mpf.make_addplot([70]*len(tmp), type='line', panel=1, color='gray', linestyle='--', width=0.5, alpha=0.3))
    
    # Add MACD components to panel 2
    apds.append(mpf.make_addplot(tmp.macd, type='line', panel=2, color='blue', ylabel='MACD (12,26,9)', width=1))
    apds.append(mpf.make_addplot(tmp.signal, type='line', panel=2, color='red', width=1))
    apds.append(mpf.make_addplot(tmp.macd_hist, type='bar', panel=2, color='dimgray', alpha=0.5))
    
    # Add ATR to panel 3
    apds.append(mpf.make_addplot(tmp.atr, type='line', panel=3, color='orange', ylabel='ATR (14)', width=1))
    
    # Add Bollinger Bands to main price panel
    apds.append(mpf.make_addplot(tmp.bb_upper, type='line', color='blue', linestyle='--', width=0.7))
    apds.append(mpf.make_addplot(tmp.bb_middle, type='line', color='blue', width=0.7))
    apds.append(mpf.make_addplot(tmp.bb_lower, type='line', color='blue', linestyle='--', width=0.7))

    # Create a custom style with larger title font and padding
    s = mpf.make_mpf_style(
        marketcolors=mpf.make_marketcolors(up='g', down='r'),
        figcolor='white',
        gridstyle=':',
        gridcolor='lightgray',
        y_on_right=True,  # Position y-axis labels on the right
        rc={'font.size': 12, 'axes.titlesize': 16, 'axes.titlepad': 20}  # Increase title size and padding
    )

    plot_kwargs = {
            'type': 'candle',
            'style': s,
            'savefig': {
                'fname': buf,
                'bbox_inches': 'tight',
                'pad_inches': 0.5,
                'dpi': 300
            },
            'axisoff': False,  # Ensure axes are turned off in the mplfinance plot
            'addplot': apds,
            'figsize':(14, 10),  # Wider figure to fill more horizontal space
            'volume': False,
            'panel_ratios': (4, 1, 1, 1),  # Ratio for main chart, RSI, MACD, ATR
            'tight_layout': True,  # Use tight layout to maximize chart area
            'main_panel': 0,
            'num_panels': 4,  # Total number of panels (main + 3 indicators)
            'fill_between': dict(y1=tmp['bb_upper'].values, y2=tmp['bb_lower'].values, alpha=0.1, color='blue'),  # Add light shading between Bollinger Bands
            'ylim': (price_min - y_margin, price_max + y_margin),  # Set y-axis limits with margin
            'figratio': (16, 9),  # 16:9 aspect ratio with more space for title
            'scale_padding': {'left': 0.1, 'top': 1.3, 'right': 0.2, 'bottom': 0.1},  # Add extra padding at the right for labels
            'datetime_format': '%b-%d %H:%M',  # Format for date labels
            'show_nontrading': False,  # Don't show non-trading periods
            'title': chart_title
        }

    # Create the plot
    fig, axes = mpf.plot(tmp, returnfig=True, **plot_kwargs)
    
    
    # Save the figure to the buffer
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    
    # Convert the image to base64
    buf.seek(0)
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    buf.seek(0)
    
    return img_base64, buf, tmp  # Return the processed DataFrame as well

def generate_trend_chart(df_data, contract, title: str = '1 Hour Trend Chart'):
    """Generate a trend-focused candlestick chart using mplfinance and return base64 encoded image"""
    # Create a figure and save it to a bytes buffer
    buf = io.BytesIO()
    
    symbol = contract.symbol
    currency = contract.currency
    pair = f"{symbol}.{currency}"

    chart_title = f"{pair} - {title}\nIndicators: EMA(20-orange,50-blue,200-red), TSI(25,13), Parabolic SAR, Support/Resistance"

    tmp = df_data.copy()
    tmp = tmp.set_index('date')
    tmp.index = pd.to_datetime(tmp.index)

    # Calculate trend-focused indicators for 1-hour timeframe
    
    # Calculate EMAs (20, 50, 200)
    tmp['ema_20'] = tmp['close'].ewm(span=20, adjust=False).mean()
    tmp['ema_50'] = tmp['close'].ewm(span=50, adjust=False).mean()
    tmp['ema_200'] = tmp['close'].ewm(span=200, adjust=False).mean()
    
    # Calculate Trend Strength Index (TSI)
    # TSI = 100 * (EMA of EMA of price change) / (EMA of EMA of absolute price change)
    price_change = tmp['close'].diff()
    abs_price_change = abs(price_change)
    
    # First smoothing
    first_smooth = price_change.ewm(span=25, adjust=False).mean()
    first_smooth_abs = abs_price_change.ewm(span=25, adjust=False).mean()
    
    # Second smoothing
    second_smooth = first_smooth.ewm(span=13, adjust=False).mean()
    second_smooth_abs = first_smooth_abs.ewm(span=13, adjust=False).mean()
    
    # Calculate TSI
    tmp['tsi'] = 100 * (second_smooth / second_smooth_abs)
    
    # Calculate Parabolic SAR using talib (simple and reliable)
    tmp['psar'] = talib.SAR(tmp['high'].values, tmp['low'].values, acceleration=0.02, maximum=0.2)
    
    # Calculate Support and Resistance levels (simplified)
    # Use recent highs and lows as potential levels
    lookback = 20
    tmp['resistance'] = tmp['high'].rolling(window=lookback).max()
    tmp['support'] = tmp['low'].rolling(window=lookback).min()
    
    # Drop any rows with NA values
    tmp = tmp.dropna()
    tmp = tmp.tail(50)  # Show 50 bars to match 15-minute chart
    
    # Calculate y-axis limits with extra margin
    price_min = min(tmp['low'].min(), tmp['support'].min())
    price_max = max(tmp['high'].max(), tmp['resistance'].max())
    price_range = price_max - price_min
    y_margin = price_range * 0.1  # Add 10% margin
    
    # Create a list of addplots for trend indicators
    apds = []
    
    # Add EMAs to main panel
    apds.append(mpf.make_addplot(tmp.ema_20, type='line', color='orange', width=1.5, label='EMA 20'))
    apds.append(mpf.make_addplot(tmp.ema_50, type='line', color='blue', width=1.5, label='EMA 50'))
    apds.append(mpf.make_addplot(tmp.ema_200, type='line', color='red', width=2, label='EMA 200'))
    
    # Add Parabolic SAR
    apds.append(mpf.make_addplot(tmp.psar, type='scatter', color='green', markersize=20, marker='o'))
    
    # Add Support and Resistance levels
    apds.append(mpf.make_addplot(tmp.resistance, type='line', color='red', linestyle='--', width=1, alpha=0.7))
    apds.append(mpf.make_addplot(tmp.support, type='line', color='green', linestyle='--', width=1, alpha=0.7))
    
    # Add TSI to panel 1
    apds.append(mpf.make_addplot(tmp.tsi, type='line', panel=1, color='purple', ylabel='TSI', width=1.5))
    
    # Add TSI signal line (EMA of TSI)
    tsi_signal = tmp.tsi.ewm(span=7, adjust=False).mean()
    apds.append(mpf.make_addplot(tsi_signal, type='line', panel=1, color='orange', width=1))
    
    # Add zero line for TSI
    apds.append(mpf.make_addplot([0]*len(tmp), type='line', panel=1, color='gray', linestyle='-', width=0.5, alpha=0.5))
    
    # Add TSI histogram
    tsi_hist = tmp.tsi - tsi_signal
    apds.append(mpf.make_addplot(tsi_hist, type='bar', panel=1, color='lightblue', alpha=0.6))

    # Create a custom style for trend analysis
    s = mpf.make_mpf_style(
        marketcolors=mpf.make_marketcolors(up='g', down='r'),
        figcolor='white',
        gridstyle=':',
        gridcolor='lightgray',
        y_on_right=True,
        rc={'font.size': 12, 'axes.titlesize': 16, 'axes.titlepad': 20}
    )

    plot_kwargs = {
        'type': 'candle',
        'style': s,
        'savefig': {
            'fname': buf,
            'bbox_inches': 'tight',
            'pad_inches': 0.5,
            'dpi': 300
        },
        'axisoff': False,
        'addplot': apds,
        'figsize': (16, 12),  # Larger figure for trend analysis
        'volume': False,
        'panel_ratios': (6, 1),  # Ratio for main chart and TSI
        'tight_layout': True,
        'main_panel': 0,
        'num_panels': 2,  # Total number of panels (main + TSI)
        'ylim': (price_min - y_margin, price_max + y_margin),
        'figratio': (16, 9),
        'scale_padding': {'left': 0.1, 'top': 1.3, 'right': 0.2, 'bottom': 0.1},
        'datetime_format': '%b-%d %H:%M',
        'show_nontrading': False,
        'title': chart_title
    }

    # Create the plot
    fig, axes = mpf.plot(tmp, returnfig=True, **plot_kwargs)
    
    # Add legend for EMAs
    axes[0].legend(['EMA 20', 'EMA 50', 'EMA 200'], loc='upper left')
    
    # Save the figure to the buffer
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    
    # Convert the image to base64
    buf.seek(0)
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    buf.seek(0)
    
    return img_base64, buf, tmp  # Return the processed DataFrame as well

def get_chart_analysis(pair, img_base64, df_data, timeframe="15min"):
    """Get technical analysis of the chart from LLaVA model"""
    # Get the last 5 rows of data with all indicators
    last_rows = df_data.tail(5).copy()
    
    # Convert DataFrame to JSON string with 'split' orientation for cleaner output
    # and round all numeric values to 5 decimal places
    json_data = last_rows.round(5).to_json(orient='records', date_format='iso')
    
    # Load the appropriate prompt template based on timeframe
    if timeframe == "15min":
        prompt_template = load_prompt('chart_analysis_15min')
    else:
        prompt_template = load_prompt('chart_analysis')
    
    if prompt_template is None:
        return "Error loading chart analysis prompt"
    
    # Format the prompt with the data
    prompt = prompt_template.format(pair=pair, json_data=json_data)
    
    logger.debug(f"prompt: {prompt}")
    payload = {
        "model": "llava:13b",
        "prompt": prompt,
        "images": [img_base64],
        "stream": False
    }
    
    # Send request to Ollama
    response = requests.post(
        "http://ollama:11434/api/generate",
        json=payload
    )
    
    if response.status_code == 200:
        result = response.json()
        analysis_text = result.get('response', '')
        logger.info(f"Chart analysis received from LLaVA for {timeframe} timeframe")
        return analysis_text
    else:
        logger.error(f"Failed to get analysis from Ollama: {response.status_code}")
        return "Error getting chart analysis from Ollama"

def get_trading_recommendation(symbol, analysis_text):
    """Extract trading recommendation directly from Sonnet's JSON analysis"""
    import json
    import re
    
    logger.info(f"Extracting trading recommendation from Sonnet analysis for {symbol}")
    logger.debug(f"Raw analysis text: {analysis_text}")
    
    # Try to extract JSON from the analysis text
    try:
        # Look for JSON block in the analysis (between ```json and ``` or just the JSON object)
        json_pattern = r'```json\s*(\{.*?\})\s*```|(\{[^}]*"action"[^}]*\})'
        json_match = re.search(json_pattern, analysis_text, re.DOTALL)
        
        if json_match:
            # Use the first non-None group
            json_str = json_match.group(1) if json_match.group(1) else json_match.group(2)
            logger.info(f"Found JSON block: {json_str}")
            
            # Parse the JSON
            json_data = json.loads(json_str)
            
            # Extract the action field and convert to constant
            action_str = json_data.get('action', 'NONE').upper()
            logger.info(f"Extracted action from JSON: {action_str}")
            
            # Convert to action constants
            if action_str == 'LONG':
                json_data['action'] = LONG
                logger.info("Sonnet recommends LONG - using directly")
            elif action_str == 'SHORT':
                json_data['action'] = SHORT
                logger.info("Sonnet recommends SHORT - using directly")
            else:
                json_data['action'] = NONE
                logger.info("Sonnet recommends NONE - using directly")
            
            # Return the complete dictionary with all fields
            return json_data
            
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from Sonnet analysis: {e}")
    except Exception as e:
        logger.error(f"Error extracting recommendation from analysis: {e}")
    
    # Fallback: try to find action words in the text directly
    logger.info("Falling back to text-based extraction")
    analysis_upper = analysis_text.upper()
    
    # Look for quoted action values first (most reliable)
    if '"action": "LONG"' in analysis_text or '"action":"LONG"' in analysis_text:
        logger.info("Found LONG in JSON action field - using fallback extraction")
        return {
            'action': LONG,
            'value_estimate': 0.0,
            'recommendation': "LONG"
        }
    elif '"action": "SHORT"' in analysis_text or '"action":"SHORT"' in analysis_text:
        logger.info("Found SHORT in JSON action field - using fallback extraction")
        return {
            'action': SHORT,
            'value_estimate': 0.0,
            'recommendation': "SHORT"
        }
    
    # Final fallback - default to NONE
    logger.info("Could not extract clear recommendation - defaulting to NONE")
    return {
        'action': NONE,
        'value_estimate': 0.0,
        'recommendation': "NONE"
    }

def get_ollama_prediction(pair, img_base64_15min, contract, processed_df_15min, img_base64_trend, processed_df_trend):
    """Multi-timeframe analysis: pass both charts to AI for single comprehensive analysis"""
    # Get the last 5 rows of data with all indicators for both timeframes
    last_rows_15min = processed_df_15min.tail(5).copy()
    last_rows_trend = processed_df_trend.tail(5).copy()
    
    # Convert both DataFrames to JSON strings
    json_data_15min = last_rows_15min.round(5).to_json(orient='records', date_format='iso')
    json_data_trend = last_rows_trend.round(5).to_json(orient='records', date_format='iso')
    
    # Load the multi-timeframe analysis prompt
    prompt_template = load_prompt('multi_timeframe_analysis')
    if prompt_template is None:
        return {
            'action': NONE,
            'value_estimate': 0.0,
            'reasoning': "Error loading multi-timeframe analysis prompt"
        }
    
    # Format the prompt with both datasets
    prompt = prompt_template.format(
        pair=pair, 
        json_data_15min=json_data_15min,
        json_data_trend=json_data_trend
    )
    
    logger.debug(f"Multi-timeframe prompt: {prompt}")
    
    # Send both charts to LLaVA for comprehensive analysis
    payload = {
        "model": "llava:13b",
        "prompt": prompt,
        "images": [img_base64_15min, img_base64_trend],  # Pass both charts
        "stream": False
    }
    
    # Send request to Ollama
    response = requests.post(
        "http://ollama:11434/api/generate",
        json=payload
    )
    
    if response.status_code == 200:
        result = response.json()
        analysis_text = result.get('response', '')
        logger.info(f"Multi-timeframe analysis received from LLaVA")
        
        # Get trading recommendation based on the comprehensive analysis
        recommendation = get_trading_recommendation(pair, analysis_text)
        
        # Use the comprehensive analysis as the reasoning
        recommendation_word = recommendation.get('recommendation', 'NONE')
        full_response = f"RECOMMENDATION: {recommendation_word}\n\nMULTI-TIMEFRAME ANALYSIS:\n{analysis_text}"
        
        return {
            'action': recommendation['action'],
            'value_estimate': recommendation['value_estimate'],
            'reasoning': full_response
        }
    else:
        logger.error(f"Failed to get multi-timeframe analysis from Ollama: {response.status_code}")
        return {
            'action': NONE,
            'value_estimate': 0.0,
            'reasoning': "Error getting multi-timeframe analysis from Ollama"
        }

def get_sonnet_prediction(pair, img_base64_15min, contract, processed_df_15min, img_base64_trend, processed_df_trend):
    """Multi-timeframe analysis using Anthropic's Sonnet model for enhanced analysis"""
    try:
        # Get API key from environment
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not found in environment variables")
            return {
                'action': NONE,
                'value_estimate': 0.0,
                'reasoning': "ANTHROPIC_API_KEY not configured"
            }
        
        # Initialize Anthropic client
        client = Anthropic(api_key=api_key)
        
        # Get the last 5 rows of data with all indicators for both timeframes
        last_rows_15min = processed_df_15min.tail(5).copy()
        last_rows_trend = processed_df_trend.tail(5).copy()
        
        # Convert both DataFrames to JSON strings
        json_data_15min = last_rows_15min.round(5).to_json(orient='records', date_format='iso')
        json_data_trend = last_rows_trend.round(5).to_json(orient='records', date_format='iso')
        
        # Load the multi-timeframe analysis prompt
        prompt_template = load_prompt('multi_timeframe_analysis')
        if prompt_template is None:
            raise Exception("Error loading multi-timeframe analysis prompt")
        
        # Get pip size for this pair
        pip_size = FOREX_PAIRS.get(pair, {}).get('pip_size', 0.0001)
        
        # Format the prompt with both datasets and pip size
        prompt = prompt_template.format(
            pair=pair,
            pip_size=pip_size,
            json_data_15min=json_data_15min,
            json_data_trend=json_data_trend
        )
        
        logger.debug(f"Sonnet multi-timeframe prompt: {prompt}")
        
        # Prepare the message for Sonnet
        message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_base64_15min
                    }
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_base64_trend
                    }
                }
            ]
        }
        
        # Send request to Anthropic Sonnet
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[message]
        )
        
        analysis_text = response.content[0].text
        logger.info(f"Multi-timeframe analysis received from Anthropic Sonnet")
        
        # Get trading recommendation based on the comprehensive analysis
        recommendation = get_trading_recommendation(pair, analysis_text)
        
        # If we have a complete recommendation from JSON, return it directly
        if all(key in recommendation for key in ['action', 'entry_price', 'stop_loss', 'take_profit', 'validity_minutes', 'confidence']):
            logger.info("Returning complete recommendation from AI JSON response")
            return recommendation
        
        # Fallback for incomplete responses - use the comprehensive analysis as the reasoning
        recommendation_word = recommendation.get('recommendation', 'NONE')
        full_response = f"RECOMMENDATION: {recommendation_word}\n\nSONNET MULTI-TIMEFRAME ANALYSIS:\n{analysis_text}"
        
        return {
            'action': recommendation['action'],
            'value_estimate': recommendation.get('value_estimate', 0.0),
            'reasoning': full_response
        }
        
    except Exception as e:
        raise e

def get_ai_prediction(pair, img_base64_15min, contract, processed_df_15min, img_base64_trend, processed_df_trend, prefer_sonnet=True):
    """Smart AI prediction that automatically chooses between Ollama and Sonnet"""
    if prefer_sonnet and os.getenv('ANTHROPIC_API_KEY'):
        logger.info("Using Anthropic Sonnet for analysis")
        return get_sonnet_prediction(pair, img_base64_15min, contract, processed_df_15min, img_base64_trend, processed_df_trend)
    else:
        logger.info("Using Ollama LLaVA for analysis")
        return get_ollama_prediction(pair, img_base64_15min, contract, processed_df_15min, img_base64_trend, processed_df_trend)

def can_trade_with_open_positions(open_trades, current_pair, new_direction, correlation_matrix, threshold=0.5):
    """
    Check if it's safe to trade a new pair given existing open trades and correlation matrix.
    Now considers trade direction to allow hedging while blocking concentration risk.
    
    Args:
        open_trades: List of open trade objects with symbol and direction attributes
        current_pair: String representing the pair to be traded (e.g., "EUR.USD")
        new_direction: Direction of new trade (LONG=1 or SHORT=2) - REQUIRED
        correlation_matrix: Pandas DataFrame with correlation matrix
        threshold: Maximum allowed absolute correlation for concentration risk (default: 0.5)
    
    Returns:
        dict: {
            'can_trade': bool,
            'reason': str,
            'correlations': list of tuples (pair1, pair2, correlation),
            'max_correlation': float
        }
    """
    try:
        # VALIDATION - Fail loudly if parameters missing
        if new_direction is None:
            raise ValueError("new_direction is required but was None")
        if new_direction not in [LONG, SHORT]:
            raise ValueError(f"new_direction must be LONG(1) or SHORT(2), got: {new_direction}")
        if current_pair is None or current_pair == "":
            raise ValueError(f"current_pair is required but was: {current_pair}")
        if correlation_matrix is None or correlation_matrix.empty:
            raise ValueError("correlation_matrix is required but is None or empty")
        
        # If no open trades, always allow trading
        if not open_trades:
            return {
                'can_trade': True,
                'reason': 'No open trades - safe to trade',
                'correlations': [],
                'max_correlation': 0.0
            }
        
        # Check each open trade for concentration risk vs hedging opportunity
        correlations = []
        max_correlation = 0.0
        
        for trade in open_trades:
            try:
                # Get correlation between current pair and open trade pair
                correlation = correlation_matrix.loc[current_pair, trade.symbol]
                abs_correlation = abs(correlation)
                
                correlations.append((current_pair, trade.symbol, correlation))
                
                if abs_correlation > max_correlation:
                    max_correlation = abs_correlation
                
                # Check if this creates concentration risk
                if abs_correlation > threshold:
                    is_concentration_risk = False
                    
                    if correlation > 0:  # Positive correlation
                        # Concentration risk if same direction (both move together)
                        is_concentration_risk = (trade.direction == new_direction)
                    else:  # Negative correlation
                        # Concentration risk if opposite directions (both profit from same market move)
                        is_concentration_risk = (trade.direction != new_direction)
                    
                    if is_concentration_risk:
                        direction_name = "LONG" if new_direction == LONG else "SHORT"
                        existing_direction_name = "LONG" if trade.direction == LONG else "SHORT"
                        return {
                            'can_trade': False,
                            'reason': f'Concentration risk: {direction_name} {current_pair} vs {existing_direction_name} {trade.symbol} (corr={correlation:.3f})',
                            'correlations': correlations,
                            'max_correlation': abs_correlation
                        }
                    
            except KeyError as e:
                logger.warning(f"Pair {e} not found in correlation matrix")
                continue
            except Exception as e:
                logger.error(f"Error calculating correlation for {current_pair} vs {trade.symbol}: {e}")
                continue
        
        # If we get here, no concentration risk found - allow trade
        direction_name = "LONG" if new_direction == LONG else "SHORT"
        if correlations:
            reason = f"Safe to trade {direction_name} {current_pair} - creates hedging/diversification with existing positions"
        else:
            reason = f"Safe to trade {direction_name} {current_pair} - no correlation data available"
        
        return {
            'can_trade': True,
            'reason': reason,
            'correlations': correlations,
            'max_correlation': max_correlation
        }
        
    except Exception as e:
        logger.error(f"Error in can_trade_with_open_positions: {e}")
        return {
            'can_trade': False,
            'reason': f'Error checking correlations: {str(e)}',
            'correlations': [],
            'max_correlation': float('inf')
        }