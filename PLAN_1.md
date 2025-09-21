# Simplified ORB Strategy Implementation Plan

## Overview
Implement a simplified Opening Range Breakout (ORB) strategy with clear rules:
- Static list of stocks (no pre-market scanning)
- Configurable opening range timeframe (15m, 30m, or 60m)
- Breakout detection on close above/below range
- Fixed risk/reward ratios with trailing stop

## Core Strategy Rules

### 1. Entry Conditions
- **Opening Range**: First 15, 30, or 60 minutes after market open (configurable)
- **Breakout Signal**: Candle closes above range high (long) or below range low (short)
- **Range Validation**:
  - Minimum range: 0.5% of stock price
  - Maximum range: 3% of stock price

### 2. Risk Management
- **Stop Loss**: Middle of opening range (50% retracement) - **Actual IB stop order**
- **Take Profit**: 1.5x opening range size from entry - **Monitored price level (not an order)**
- **Trailing Stop**: After TP hit, trail at 0.5x opening range size - **Modify existing stop order**
- **Position Sizing**: Based on account risk percentage (configurable)
- **Max Positions**: Configurable limit on concurrent positions

### 3. Exit Conditions
- Stop loss hit
- Take profit hit (then switch to trailing)
- End of day (12:50 PM PST)
- Time-based exit (position stagnant >90 minutes)

## Implementation Components

### 1. Configuration Updates

#### `src/core/constants.py`
```python
# Add new constants
CONFIG_ORB_TIMEFRAME = "orb_timeframe"  # 15, 30, or 60 minutes
CONFIG_MIN_RANGE_PCT = "min_range_pct"  # Minimum range as % of price
CONFIG_MAX_RANGE_PCT = "max_range_pct"  # Maximum range as % of price
CONFIG_TRAILING_STOP_RATIO = "trailing_stop_ratio"  # 0.5x of range
CONFIG_TAKE_PROFIT_RATIO = "take_profit_ratio"  # 1.5x of range
CONFIG_STOCK_LIST = "stock_list"  # Static list of symbols

# New event types
EVENT_TYPE_CHECK_BREAKOUT = "EVENT_TYPE_CHECK_BREAKOUT"
EVENT_TYPE_ACTIVATE_TRAILING_STOP = "EVENT_TYPE_ACTIVATE_TRAILING_STOP"
```

### 2. Static Stock Configuration

#### `src/stocks/stocks_config.py` (NEW FILE)
```python
# Static list of stocks to trade
STOCK_SYMBOLS = [
    "AAPL",  # Apple
    "MSFT",  # Microsoft
    "GOOGL", # Google
    "AMZN",  # Amazon
    "NVDA",  # NVIDIA
    "TSLA",  # Tesla
    "META",  # Meta
    "AMD",   # AMD
    "SPY",   # S&P 500 ETF
    "QQQ",   # NASDAQ ETF
]

# Stock-specific configurations (optional)
STOCK_CONFIGS = {
    "TSLA": {
        "min_range_pct": 1.0,  # More volatile, needs bigger range
        "max_range_pct": 5.0
    },
    "SPY": {
        "min_range_pct": 0.3,  # Less volatile ETF
        "max_range_pct": 2.0
    }
}
```

### 3. Command Implementations

#### `CalculateOpeningRangeCommand`
**Logic:**
1. Wait for configured timeframe to pass (15/30/60 min after open)
2. For each stock in static list:
   - Fetch historical bars for opening period
   - Calculate high/low of period
   - Calculate range size and percentage
   - Validate range (not too big/small)
   - Store valid ranges in database
3. Send notification with calculated ranges

**Key Methods:**
- `_calculate_range_for_symbol(symbol, timeframe_minutes)`
- `_validate_range(range_high, range_low, current_price)`
- `_get_opening_period_bars(symbol, minutes)`

#### `ORBStrategyCommand`
**Logic:**
1. Check current time is after opening range period
2. For each stock with valid opening range:
   - Get current price (real-time quote)
   - Check if previous candle closed above/below range
   - Validate market conditions (optional)
   - Check position limits
   - If breakout confirmed:
     - Calculate position size
     - Set stop loss at range midpoint
     - Set take profit at 1.5x range
     - Execute trade
3. Store trade details in database

**Key Methods:**
- `_check_breakout(symbol, opening_range, current_bar)`
- `_calculate_position_size(range_size, account_value)`
- `_execute_orb_trade(symbol, direction, entry, stop, target)`

#### `ManageStockPositionsCommand`
**Logic:**
1. Query all open positions from database
2. For each position:
   - Get current price (real-time quote)
   - **If NOT trailing yet**: Check if current price >= take_profit_price (from DB)
     - If yes, set trailing_stop_active = True
     - Call modify_stop_order() to move stop to (current_price - 0.5x range_size)
   - **If already trailing**: Check if price moved higher
     - Calculate new stop: current_price - (0.5 * range_size)
     - If new stop > current stop, call modify_stop_order()
   - Check time-based exit (>90 min stagnant)
   - Check end-of-day exit (12:50 PM PST)
3. IB handles stop loss hits automatically (no action needed)

**Key Methods:**
- `_check_take_profit_level(position, current_price)` - Monitor TP level
- `_activate_trailing_stop(position, current_price)` - Start trailing
- `_update_trailing_stop(position, current_price)` - Continue trailing
- `_should_exit_for_time(position)`

### 4. Service Layer Updates

#### `StocksStrategyService`
**New Methods:**
```python
def calculate_opening_range(self, symbol, timeframe_minutes):
    """
    Calculate opening range for a symbol
    Returns: {
        'symbol': str,
        'range_high': float,
        'range_low': float,
        'range_mid': float,
        'range_size': float,
        'range_pct': float,
        'valid': bool,
        'reason': str  # If invalid
    }
    """

def check_breakout_signal(self, symbol, opening_range, current_price, previous_close):
    """
    Check if breakout conditions are met
    Returns: {
        'signal': 'LONG'|'SHORT'|'NONE',
        'entry_price': float,
        'stop_loss': float,
        'take_profit': float,
        'range_size': float
    }
    """

def calculate_position_parameters(self, signal_info, account_value, risk_pct):
    """
    Calculate position size and risk parameters
    Returns: {
        'shares': int,
        'risk_amount': float,
        'potential_profit': float,
        'risk_reward_ratio': float
    }
    """
```

### 5. IBClient Additions

#### `src/core/ibclient.py`
**New Methods Required:**

```python
def get_stock_bars(self, symbol, duration_minutes=60, bar_size="1 min", timeout=10):
    """
    Get historical bars for a stock (wrapper around existing get_historic_data)
    Args:
        symbol: Stock symbol
        duration_minutes: Number of minutes to fetch (e.g., 60 for 1 hour)
        bar_size: Bar size (e.g., "1 min", "5 mins")
    Returns:
        DataFrame with OHLCV data
    """

def place_stock_entry_with_stop(self, symbol, action, quantity, entry_price, stop_price):
    """
    Place ONLY entry and stop orders (NO take profit order)
    Take profit is monitored by position manager, not placed as order
    Args:
        symbol: Stock symbol
        action: "BUY" or "SELL"
        quantity: Number of shares
        entry_price: Limit price for entry
        stop_price: Stop loss price
    Returns:
        Dict with {'parent_order_id': xxx, 'stop_order_id': xxx}
    """

def modify_stop_order(self, order_id, new_stop_price):
    """
    Modify an existing stop order (for trailing stops)
    Used to implement trailing stop by moving existing stop order
    Args:
        order_id: Stop order ID to modify
        new_stop_price: New stop price
    Returns:
        Success boolean
    """
```

**Note:** We'll use existing methods for:
- Account value: `get_pair_balance("USD")`
- Current price: `get_stock_market_data()` or `get_stock_price()`
- Positions: Track in database, reconcile with IB periodically

### 6. Database Schema

#### New Tables
```sql
-- Opening ranges table
CREATE TABLE opening_ranges (
    id INTEGER PRIMARY KEY,
    symbol VARCHAR(10),
    date DATE,
    timeframe_minutes INTEGER,
    range_high DECIMAL(10,2),
    range_low DECIMAL(10,2),
    range_mid DECIMAL(10,2),
    range_size DECIMAL(10,2),
    range_pct DECIMAL(5,2),
    is_valid BOOLEAN,
    invalid_reason VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Positions table
CREATE TABLE positions (
    id INTEGER PRIMARY KEY,
    symbol VARCHAR(10),
    direction VARCHAR(10),  -- 'LONG' or 'SHORT'
    entry_time TIMESTAMP,
    entry_price DECIMAL(10,2),
    shares INTEGER,
    stop_loss_price DECIMAL(10,2),
    take_profit_price DECIMAL(10,2),
    trailing_stop_active BOOLEAN DEFAULT FALSE,
    trailing_stop_price DECIMAL(10,2),
    take_profit_hit BOOLEAN DEFAULT FALSE,
    range_size DECIMAL(10,2),
    current_price DECIMAL(10,2),
    unrealized_pnl DECIMAL(10,2),
    status VARCHAR(20),  -- 'OPEN', 'CLOSED', 'PENDING'
    exit_time TIMESTAMP,
    exit_price DECIMAL(10,2),
    exit_reason VARCHAR(100),
    realized_pnl DECIMAL(10,2),
    parent_order_id INTEGER,
    stop_order_id INTEGER,
    target_order_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trade signals table (for tracking)
CREATE TABLE trade_signals (
    id INTEGER PRIMARY KEY,
    symbol VARCHAR(10),
    signal_time TIMESTAMP,
    signal_type VARCHAR(10),  -- 'LONG', 'SHORT'
    opening_range_id INTEGER,
    breakout_price DECIMAL(10,2),
    entry_price DECIMAL(10,2),
    stop_loss DECIMAL(10,2),
    take_profit DECIMAL(10,2),
    position_size INTEGER,
    executed BOOLEAN DEFAULT FALSE,
    execution_time TIMESTAMP,
    position_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (opening_range_id) REFERENCES opening_ranges(id),
    FOREIGN KEY (position_id) REFERENCES positions(id)
);
```

### 7. Execution Flow

#### Market Open (6:30 AM PST)
1. System connects to IB Gateway
2. Subscribes to real-time data for all stocks in list
3. Waits for opening range period

#### After Opening Range (6:45/7:00/7:30 AM PST)
1. Calculate opening ranges for all stocks
2. Store valid ranges in database
3. Begin monitoring for breakouts

#### Breakout Monitoring (Every 1-5 minutes)
1. Check each stock for breakout
2. Validate breakout (close above/below range)
3. Execute trades with entry + stop orders only (NO take profit order)
4. Store position details with take_profit_price in database

#### Position Management (Continuous)
1. Monitor positions vs take_profit_price (from database)
2. When current price >= TP level: activate trailing stop (modify existing stop order)
3. Continue trailing: update stop order as price moves up
4. Handle time-based and EOD exits

#### Market Close (12:50 PM PST)
1. Close all remaining positions
2. Generate daily report
3. Clean up subscriptions

## Testing Strategy

### Unit Tests
- Range calculation with various timeframes
- Breakout detection logic
- Position sizing calculations
- Stop/target price calculations

### Integration Tests
- IB API connection and data retrieval
- Order placement and modification
- Database operations
- Real-time data handling

### Paper Trading Tests
1. Run with IB paper account
2. Monitor for:
   - Correct range calculations
   - Accurate breakout detection
   - Proper order execution
   - Trailing stop functionality
3. Verify all exits work correctly

## Risk Controls

### Pre-Trade Checks
- Valid opening range exists
- Range within min/max bounds
- Account has sufficient buying power
- Position limit not exceeded
- Symbol is tradeable

### Post-Trade Monitoring
- Stop loss order confirmed
- Position tracked in database with take_profit_price
- Real-time P&L monitoring
- Circuit breaker for daily loss limit
- **Note**: No take profit order placed with IB - monitored in code

## Configuration Parameters

```python
# Main configuration
CONFIG = {
    # ORB Parameters
    "orb_timeframe": 30,  # 15, 30, or 60 minutes
    "min_range_pct": 0.5,  # Minimum range as % of price
    "max_range_pct": 3.0,  # Maximum range as % of price

    # Risk Management
    "risk_percentage": 1.0,  # Risk per trade as % of account
    "max_positions": 5,  # Maximum concurrent positions
    "take_profit_ratio": 1.5,  # TP at 1.5x range
    "trailing_stop_ratio": 0.5,  # Trail at 0.5x range

    # Filters
    "min_price": 10.0,  # Minimum stock price
    "max_price": 500.0,  # Maximum stock price
    "min_volume": 1000000,  # Minimum daily volume

    # Timing
    "market_open": "06:30",  # PST
    "market_close": "12:50",  # PST (early close for safety)
    "max_hold_minutes": 90,  # Exit if stagnant
}
```

## Implementation Priority

1. **Phase 1: Core Infrastructure**
   - ✅ **COMPLETE**: Configuration and constants
   - ✅ **COMPLETE**: Static stock list created
   - 🔄 **NEXT**: IBClient methods for stocks
   - Database schema

2. **Phase 2: Opening Range**
   - Calculate opening range command
   - Range validation logic
   - Database storage

3. **Phase 3: Breakout Detection**
   - ORB strategy command
   - Breakout validation
   - Signal generation

4. **Phase 4: Order Execution**
   - Entry + stop order placement
   - Position tracking
   - Initial risk management

5. **Phase 5: Advanced Features**
   - Trailing stop implementation
   - Time-based exits
   - Performance tracking

## Success Metrics

- Opening ranges calculated correctly
- Breakouts detected accurately
- Orders executed at expected prices
- Stop losses and take profits honored
- Trailing stops adjust properly
- All positions closed by EOD
- Risk per trade stays within limits
- Daily loss limits respected