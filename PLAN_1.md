# Simplified ORB Strategy Implementation Plan

## Overview
Implement a simplified Opening Range Breakout (ORB) strategy with clear rules:
- Static list of stocks (no pre-market scanning)
- Configurable opening range timeframe (15m, 30m, or 60m)
- Breakout detection on close above/below range
- Fixed risk/reward ratios with trailing stop

## 📌 IMPORTANT: Document Maintenance
**Always update this document when implementation work is completed!**
This plan serves as the living documentation of the ORB strategy implementation.
Update status markers, add implementation notes, and document any deviations from the plan.

## Error Handling Pattern
All Commands and Services follow the error handling pattern documented in `CLAUDE.md`:
- **Raise exceptions** on failures (don't return None/False)
- **Let exceptions propagate** to CommandInvoker for consistent handling
- **No try/catch** in commands unless handling specific recoverable errors
- **Commands fail entirely** on any error (no partial success)
- **No recovery attempts** - strict exception propagation

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
EVENT_TYPE_OPEN_POSITION = "EVENT_TYPE_OPEN_POSITION"  # Published by signal commands
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

### 3. Command Implementations (6 Commands)

#### `CalculateOpeningRangeCommand` ✅ **IMPLEMENTED**
**Logic:**
1. Run at precise time based on CONFIG_ORB_TIMEFRAME:
   - 15-minute ORB → Calculate at 6:45 AM PST
   - 30-minute ORB → Calculate at 7:00 AM PST
   - 60-minute ORB → Calculate at 7:30 AM PST
2. For each stock in static STOCK_SYMBOLS list:
   - Fetch **1 single bar** matching CONFIG_ORB_TIMEFRAME (e.g., "30 mins" bar)
   - Extract high/low from that single bar
   - Calculate range size and percentage using midpoint: `(size / mid) * 100`
   - Validate range against stock-specific min/max thresholds
   - **Skip invalid ranges** (don't store in database)
   - Store only valid ranges with timeframe_minutes
3. Send PrettyTable notification with Symbol and Range % columns
4. **No try/catch** - let exceptions propagate per CLAUDE.md

**Implementation Notes:**
- Uses `IBClient.get_stock_bars()` with matching timeframe
- Range percentage calculated as: `(range_size / range_midpoint) * 100`
- Stock-specific validation from `stocks_config.py`
- Telegram notifications use `<pre>` tag for formatting
- Invalid ranges logged but not stored

**Key Methods:**
- `_calculate_range_for_symbol(symbol, timeframe_minutes)` - Process single stock
- `_validate_range(range_size_pct, stock_config)` - Stock-specific validation
- `_is_valid_calculation_time(now, timeframe_minutes)` - Dynamic timing
- `_send_notification(valid_ranges, timeframe_minutes, now)` - PrettyTable format

#### `ORBSignalCommand` ✅ **IMPLEMENTED** (renamed from ORBStrategyCommand)
**Logic:**
1. Run on **clock-aligned intervals** based on CONFIG_ORB_TIMEFRAME:
   - 15-minute: Check at :00, :15, :30, :45
   - 30-minute: Check at :00, :30
   - 60-minute: Check at :00
2. For each stock in STOCK_SYMBOLS with valid opening range:
   - Get previous candle data using `IBClient.get_stock_bars()`
   - Check if **previous candle closed** above range_high (long) or below range_low (short)
   - Check position limits via `get_open_positions_count()`
   - If breakout confirmed:
     - Calculate position size based on account risk
     - Set stop loss at range midpoint
     - Set take profit at 1.5x range from entry
     - **Publish EVENT_TYPE_OPEN_POSITION** (don't execute directly)
3. **No order placement** - signal detection only

**Key Methods (IMPLEMENTED):**
- `_analyze_stock_for_breakout(symbol, strategy_service, ib_client, now)` - Analyze single stock
- `_check_breakout_signal(opening_range, previous_close)` - Detect breakout signal
- `_publish_position_signal(symbol, breakout_signal, opening_range)` - Publish EVENT_TYPE_OPEN_POSITION
- `_is_clock_aligned_time(now)` - Check if execution time is aligned to timeframe
- `_check_position_limits()` - Query database for current open positions count

**Implementation Notes:**
- Uses STOCK_SYMBOLS directly instead of candidate-based approach
- Clock-aligned execution ensures breakouts checked at proper intervals
- Previous bar analysis prevents false signals from incomplete candles
- Event-driven architecture separates signal detection from execution
- Integrated with database for position limit checking

#### `OpenPositionCommand` ✅ **IMPLEMENTED** (strategy-agnostic position entry)
**Logic:**
1. Listen for EVENT_TYPE_OPEN_POSITION events
2. Validate event data (symbol, action, prices, etc.)
3. Check position limits (margin checks deferred with TODO comments)
4. Call IBClient.place_stock_entry_with_stop()
5. Create Position record in database with order IDs
6. Send confirmation notifications
7. **No try/catch** - let exceptions propagate per CLAUDE.md

**Key Methods (IMPLEMENTED):**
- `_validate_position_request(event_data)` - Validate 10 required fields and data types
- `_check_position_limits()` - Check max open positions via StocksStrategyService
- `_send_confirmation_notification(event_data, order_result)` - Telegram notifications

**Implementation Notes:**
- File: `src/stocks/commands/open_position_command.py`
- Strategy-agnostic design works with any signal publishing strategy
- Comprehensive validation of all event data fields
- TODO comments added for future margin requirement checks
- Integrated with orb_strategy_controller.py for EVENT_TYPE_OPEN_POSITION routing

**EVENT_TYPE_OPEN_POSITION Data:**
```python
{
    "strategy": "ORB",
    "symbol": "AAPL",
    "action": "BUY" or "SELL",
    "quantity": 100,
    "entry_price": 150.50,
    "stop_loss": 149.00,
    "take_profit": 152.00,
    "range_size": 1.50,
    "opening_range_id": 123,
    "reason": "ORB breakout above range high"
}
```

#### `ManageStockPositionsCommand` ✅ **IMPLEMENTED** (Refactored - Single Responsibility)
**Logic:**
1. Monitor position state transitions: PENDING → OPEN → CLOSED
2. Get all PENDING positions from database
   - Check if parent order filled via IBClient
   - If filled: Update status to OPEN with entry_price and entry_time
3. Get all OPEN positions from database
   - Check if stop order filled (position closed)
   - If closed: Update status to CLOSED with exit details
   - Calculate realized P&L
   - Send notification
4. **NO stop management** - handled by MoveStopOrderCommand
5. **NO exit logic** - handled by exit commands

**Key Methods:**
- `_check_order_status(order_id)` - Query IB for order status
- `_transition_to_open(position, fill_price)` - PENDING → OPEN
- `_transition_to_closed(position, exit_price, reason)` - OPEN → CLOSED
- `_calculate_realized_pnl(position, exit_price)` - Final P&L calculation

**Runs:** Every 30 seconds

**Implementation Notes:**
- File: `src/stocks/commands/manage_stock_positions_command.py`
- Refactored to handle ONLY state transitions (PENDING → OPEN → CLOSED)
- Removed all exit logic, stop management, and try/catch blocks per CLAUDE.md
- Added clean transition methods: `_transition_to_open()` and `_transition_to_closed()`
- Uses IBClient.get_order_by_id() to check order status
- Calculates realized P&L with proper long/short logic
- Integrated with stocks.py scheduling (every 30 seconds)

#### `MoveStopOrderCommand` ✅ **IMPLEMENTED** (NEW - Single Responsibility)
**Logic:**
1. Query all OPEN positions from database
2. For each position:
   - Get current price from IBClient
   - **If NOT trailing yet** (stop_moved = False):
     - Check if current price >= take_profit_price
     - If yes: Move stop to trailing level, set stop_moved = True
   - **If already trailing** (stop_moved = True):
     - Check if price moved favorably
     - If yes: Move stop to new trailing level
3. Call IBClient.modify_stop_order() for any stop modifications

**Key Methods:**
- `_should_move_stop(position, current_price)` - Determine if stop should be moved
- `_calculate_new_stop_price(position, current_price)` - Calculate new stop level
- `_move_stop_order(position, new_stop_price)` - Call IBClient.modify_stop_order()

**Configuration:**
- Uses CONFIG_TRAILING_STOP_RATIO (0.5x of range)
- Uses existing Position model fields (no DB changes needed)

**Runs:** Every minute during market hours

**Implementation Notes:**
- File: `src/stocks/commands/move_stop_order_command.py`
- Handles trailing stop modifications using CONFIG_TRAILING_STOP_RATIO
- Activates trailing when current price >= take_profit_price
- Moves stops progressively as price advances favorably
- Uses IBClient.modify_stop_order() for stop modifications
- Updates position.stop_moved and position.trailing_stop_price
- Integrated with stocks.py scheduling (every minute during market hours)

#### `TimeBasedExitCommand` ✅ **IMPLEMENTED** (NEW)
**Logic:**
1. Run every minute during market hours
2. Query all open positions from database
3. For each position:
   - Calculate how long position has been open
   - Check if position is stagnant (>90 minutes without significant price movement)
   - If stagnant, close position with market order
   - Update position record with exit_reason = "TIME_EXIT_STAGNANT"
4. Send notification for any time-based exits

**Key Methods:**
- `_is_position_stagnant(position, current_price)` - Check if position hasn't moved
- `_close_stagnant_position(position)` - Execute market order to close
- `_calculate_realized_pnl(position, exit_price)` - Calculate final P&L

**Implementation Notes:**
- File: `src/stocks/commands/time_based_exit_command.py`
- Checks positions open >90 minutes for stagnation (< 25% of range movement)
- Closes with market orders and cancels existing stop orders
- Updates exit_reason = "TIME_EXIT_STAGNANT"
- Integrated with stocks.py scheduling (every minute during market hours)

#### `EndOfDayExitCommand` ✅ **IMPLEMENTED** (NEW)
**Logic:**
1. Run at exactly 12:50 PM PST (10 minutes before market close)
2. Query all remaining open positions
3. Close all positions with market orders
4. Update position records with exit_reason = "EOD_EXIT"
5. Generate end-of-day summary report with total P&L
6. Send comprehensive daily report notification

**Key Methods:**
- `_close_position_eod(position, now)` - Close single position with market order
- `_generate_daily_report(eod_closed_positions)` - Create comprehensive P&L report
- `_format_exit_reason(exit_reason)` - Format reasons for display

**Implementation Notes:**
- File: `src/stocks/commands/end_of_day_exit_command.py`
- Closes all remaining positions with market orders at 12:50 PM PST
- Generates comprehensive daily report with PrettyTable formatting
- Includes win rate, avg win/loss, and detailed trade breakdown
- Updates exit_reason = "EOD_EXIT" for all positions
- Cancels existing stop orders before closing positions
- Integrated with stocks.py scheduling (daily at 12:50 PM PST)

### 4. Command Separation Design Principle

Each command has a single responsibility:
- **ManageStockPositionsCommand**: Position state transitions only (PENDING → OPEN → CLOSED)
- **MoveStopOrderCommand**: Stop order modifications only
- **TimeBasedExitCommand**: Stagnant position exits only (>90 minutes)
- **EndOfDayExitCommand**: EOD position exits only (12:50 PM PST)

This separation ensures:
- **Clear logging and debugging**: Each command logs its specific actions
- **Independent testing**: Can test each responsibility separately
- **Flexible scheduling**: Each command runs at its optimal frequency
- **No overlap in responsibilities**: No confusion about which command handles what
- **Easy maintenance**: Changes to one responsibility don't affect others

### 5. Service Layer Updates

#### `StocksStrategyService` ✅ **ENHANCED**
**Updated Methods:**
- `save_opening_range()` - Now includes `timeframe_minutes` parameter
- `calculate_range()` - Properly extracts OHLC from IB bar data

**New Methods Added:**
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

**Additional Methods:**
```python
def _validate_range_percentage(self, range_size_pct, stock_config):
    \"\"\"
    Validate if range size percentage is within acceptable bounds
    Returns: bool
    \"\"\"

def get_open_positions_count(self):
    \"\"\"
    Get count of currently open positions (OPEN or PENDING status)
    Returns: int
    \"\"\"
```

**Implementation Notes:**
- Range calculation uses midpoint for percentage: `(size / mid) * 100`
- Breakout detection checks previous candle close vs range high/low
- Position sizing based on account risk percentage
- Stop loss set at range midpoint, take profit at 1.5x range from entry
- Position count checking integrated for risk management

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

**Implementation Details:**
- Entry orders: MARKET (guaranteed fill on breakout)
- Stop orders: STP (stop market, guaranteed execution)
- Time in force: DAY orders (cancel at market close)
- Exchange: SMART routing for all stocks
- Order IDs: Max of IB next ID and DB max ID
- Error handling: All methods raise exceptions (see CLAUDE.md)
- No confirmation wait: Return immediately after placing orders

**We'll use existing methods for:**
- Account value: `get_pair_balance("USD")`
- Current price: `get_stock_market_data()` or `get_stock_price()`
- Position reconciliation: Periodic checks with IB API

### 6. Database Schema (SQLAlchemy Models)

#### Database Design Principles
- **Simple**: Only store what we need
- **Clean relationships**: Position.id = parent order ID
- **No redundancy**: Calculate derived values when needed

#### Models to Update/Create

**1. OpeningRange Model** (update existing)
```python
# Add ONE field to existing model:
timeframe_minutes = Column(Integer, nullable=False)  # 15, 30, or 60

# Notes:
# - Only store VALID ranges (invalid ones just logged)
# - One range per symbol per day (unique on symbol, date)
# - range_mid calculated as (range_high + range_low) / 2
```

**2. Position Model** (create new)
```python
class Position(Base):
    __tablename__ = "positions"

    # Core identification
    id = Column(Integer, primary_key=True, autoincrement=False)  # THIS IS the parent order ID!
    stop_order_id = Column(Integer, nullable=False)  # Child stop order
    opening_range_id = Column(Integer, ForeignKey('opening_ranges.id'))

    # Trade details
    symbol = Column(String(10), nullable=False)
    direction = Column(String(10), nullable=False)  # 'LONG' or 'SHORT'
    entry_time = Column(DateTime)
    entry_price = Column(Float)
    shares = Column(Integer, nullable=False)

    # Risk management
    stop_loss_price = Column(Float, nullable=False)  # Original stop price
    take_profit_price = Column(Float, nullable=False)  # Monitored level, NOT an order
    stop_moved = Column(Boolean, default=False)  # True if stop has been modified
    trailing_stop_price = Column(Float)  # Current stop price (if moved)
    range_size = Column(Float, nullable=False)  # For trailing calculations

    # Status tracking
    current_price = Column(Float)
    unrealized_pnl = Column(Float)
    status = Column(String(20), nullable=False)  # 'PENDING', 'OPEN', 'CLOSED'

    # Exit details
    exit_time = Column(DateTime)
    exit_price = Column(Float)
    exit_reason = Column(String(100))
    realized_pnl = Column(Float)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

# Key Design Notes:
# - NO parent_order_id field (id IS the parent order ID)
# - NO target_order_id field (we don't place TP orders)
# - NO trade_signals table (YAGNI - keep it simple)
# - stop_moved replaces trailing_stop_active (more meaningful)
# - Actual stop price: stop_loss_price if not moved, trailing_stop_price if moved
```

#### Database Manager Methods to Add
```python
def get_max_order_id(self):
    """Get maximum order ID for IBClient order ID calculation"""

def create_position(self, order_result, opening_range_id, take_profit_price, range_size):
    """Create position with explicit ID from order result"""

def get_pending_positions(self):
    """Get positions with status='PENDING' for order monitoring"""

def update_position_status(self, position_id, new_status, **kwargs):
    """Update position status and other fields"""

def get_open_positions(self):
    """Get positions with status='OPEN' for management"""
```

### 7. Execution Flow

#### Market Open (6:30 AM PST)
1. System connects to IB Gateway
2. Subscribes to real-time data for all stocks in list
3. Waits for opening range period

#### After Opening Range (Dynamic Based on CONFIG_ORB_TIMEFRAME)
**CalculateOpeningRangeCommand runs at:**
- **6:45 AM PST** for 15-minute ORB (after 6:30-6:45 period)
- **7:00 AM PST** for 30-minute ORB (after 6:30-7:00 period)
- **7:30 AM PST** for 60-minute ORB (after 6:30-7:30 period)

1. Fetch 1 bar matching timeframe for each stock in STOCK_SYMBOLS
2. Calculate range using: `(range_size / range_midpoint) * 100`
3. Validate against stock-specific min/max thresholds
4. Store only valid ranges with timeframe_minutes in database
5. Send PrettyTable notification with Symbol and Range %

#### Breakout Monitoring (Clock-Aligned Intervals)
**ORBSignalCommand runs on aligned intervals:**
- **15-minute ORB**: Check at :00, :15, :30, :45
- **30-minute ORB**: Check at :00, :30
- **60-minute ORB**: Check at :00

1. Check each stock's previous candle close vs opening range
2. Validate breakout (close above range_high or below range_low)
3. Publish EVENT_TYPE_OPEN_POSITION with trade parameters
4. OpenPositionCommand executes trades based on signals

#### Position Management (Continuous)
**ManageStockPositionsCommand runs periodically:**
1. Monitor positions vs take_profit_price (from database)
2. When current price >= TP level: activate trailing stop (modify existing stop order)
3. Continue trailing: update stop order as price moves up

#### Time-Based Exit Management (Every Minute)
**TimeBasedExitCommand runs every minute:**
1. Check all open positions for stagnation (>90 minutes)
2. Close stagnant positions with market orders
3. Send notifications for time-based exits

#### End-of-Day Management (12:50 PM PST)
**EndOfDayExitCommand runs at 12:50 PM PST:**
1. Close all remaining positions with market orders
2. Generate comprehensive daily P&L report
3. Send end-of-day summary notification
4. Clean up subscriptions

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

**Actual Configuration Constants (in constants.py):**
```python
# ORB Strategy Parameters
CONFIG_ORB_TIMEFRAME = "orb_timeframe"  # 15, 30, or 60 minutes
CONFIG_MIN_RANGE_PCT = "min_range_pct"  # Minimum range as % of price
CONFIG_MAX_RANGE_PCT = "max_range_pct"  # Maximum range as % of price

# Risk Management
CONFIG_TAKE_PROFIT_RATIO = "take_profit_ratio"  # 1.5x of range
CONFIG_TRAILING_STOP_RATIO = "trailing_stop_ratio"  # 0.5x of range

# Static Stock List (in stocks_config.py)
CONFIG_STOCK_LIST = "stock_list"  # Reference to STOCK_SYMBOLS

# Event Types
EVENT_TYPE_OPEN_POSITION = "EVENT_TYPE_OPEN_POSITION"  # Published by signal commands
```

**Example Configuration Values:**
```python
# In state manager or config file
{
    "orb_timeframe": 30,  # 15, 30, or 60 minutes
    "min_range_pct": 0.5,  # Default minimum range as % of price
    "max_range_pct": 3.0,  # Default maximum range as % of price
    "take_profit_ratio": 1.5,  # TP at 1.5x range
    "trailing_stop_ratio": 0.5,  # Trail at 0.5x range
}
```

**Stock-Specific Overrides (in stocks_config.py):**
```python
STOCK_CONFIGS = {
    "TSLA": {"min_range_pct": 1.0, "max_range_pct": 5.0},  # More volatile
    "SPY": {"min_range_pct": 0.3, "max_range_pct": 2.0},   # Less volatile
    # ... other overrides
}
```

## Recent Implementation Progress

### ✅ **ORBSignalCommand Completed** (January 2024)

**File:** `src/stocks/commands/strategies/orb_signal_command.py`

**Key Achievements:**
- ✅ **Renamed from ORBStrategyCommand** - Better separation of concerns
- ✅ **Direct STOCK_SYMBOLS iteration** - No longer depends on candidates table
- ✅ **Clock-aligned execution** - Only runs at proper intervals based on CONFIG_ORB_TIMEFRAME
- ✅ **Previous bar analysis** - Uses IBClient.get_stock_bars() to get completed candle data
- ✅ **Event-driven architecture** - Publishes EVENT_TYPE_OPEN_POSITION instead of direct execution
- ✅ **Database integration** - Checks position limits via get_open_positions_count()
- ✅ **Controller updated** - orb_strategy_controller.py now uses ORBSignalCommand

**Technical Implementation:**
- Uses `_is_clock_aligned_time()` to ensure execution only at :00, :15, :30, :45 (15min) or :00, :30 (30min) or :00 (60min)
- Calls `IBClient.get_stock_bars()` with proper timeframe to get previous completed bar
- Checks `previous_close > range_high` for LONG signals or `previous_close < range_low` for SHORT signals
- Calculates position size based on account risk percentage and price difference
- Publishes structured events with all necessary trade parameters

**Event Data Structure:**
```python
{
    "strategy": "ORB",
    "symbol": "AAPL",
    "action": "BUY" or "SELL",
    "quantity": 100,
    "entry_price": 150.50,
    "stop_loss": 149.00,
    "take_profit": 152.00,
    "range_size": 1.50,
    "opening_range_id": 123,
    "reason": "ORB breakout above range high"
}
```

### ✅ **OpenPositionCommand Completed** (January 2024)

**File:** `src/stocks/commands/open_position_command.py`

**Key Achievements:**
- ✅ **Strategy-agnostic design** - Works with any strategy publishing position signals
- ✅ **Complete validation** - Validates 10 required fields in event data
- ✅ **Trade execution** - Uses IBClient.place_stock_entry_with_stop()
- ✅ **Database integration** - Creates Position records with proper order IDs
- ✅ **Position limits** - Checks max open positions before execution
- ✅ **Notification system** - Sends detailed Telegram confirmations
- ✅ **Controller integration** - Registered in orb_strategy_controller.py

**Technical Implementation:**
- Listens for EVENT_TYPE_OPEN_POSITION events
- No try/catch blocks per CLAUDE.md pattern
- TODO comments added for future margin requirement checks
- Validates all numeric fields are positive
- Confirms action is either 'BUY' or 'SELL'

### ✅ **Phase 4 Position Management Completed** (January 2025)

**Complete Command Suite Implemented:**

**1. ManageStockPositionsCommand (Refactored)**
- ✅ **Single Responsibility:** Only handles state transitions (PENDING → OPEN → CLOSED)
- ✅ **Clean Architecture:** Removed all exit logic, stop management, try/catch blocks
- ✅ **Database Integration:** Uses get_pending_positions() and get_open_positions()
- ✅ **IB Integration:** Calls get_order_by_id() to check order status
- ✅ **Scheduling:** Every 30 seconds via stocks.py

**2. MoveStopOrderCommand (NEW)**
- ✅ **Trailing Logic:** Activates when current_price >= take_profit_price
- ✅ **Progressive Updates:** Moves stops as price advances favorably
- ✅ **Configuration:** Uses CONFIG_TRAILING_STOP_RATIO (0.5x range)
- ✅ **IB Integration:** Calls modify_stop_order() for stop modifications
- ✅ **Scheduling:** Every minute during market hours via stocks.py

**3. TimeBasedExitCommand (NEW)**
- ✅ **Stagnation Detection:** Closes positions open >90 minutes with <25% range movement
- ✅ **Market Orders:** Executes immediate closure with cancel_order() on stops
- ✅ **Exit Tracking:** Updates exit_reason = "TIME_EXIT_STAGNANT"
- ✅ **Scheduling:** Every minute during market hours via stocks.py

**4. EndOfDayExitCommand (NEW)**
- ✅ **EOD Closure:** Closes all positions at 12:50 PM PST with market orders
- ✅ **Daily Reporting:** Comprehensive P&L report with PrettyTable formatting
- ✅ **Analytics:** Win rate, avg win/loss, detailed trade breakdown
- ✅ **Scheduling:** Daily at 12:50 PM PST via stocks.py

**Infrastructure Achievements:**
- ✅ **New EVENT_TYPE constants:** MOVE_STOP_ORDER, TIME_BASED_EXIT, END_OF_DAY_EXIT
- ✅ **stocks.py Integration:** All commands properly scheduled with market_open checks
- ✅ **Controller Registration:** All commands registered in orb_strategy_controller.py
- ✅ **Error Handling:** No try/catch blocks per CLAUDE.md pattern
- ✅ **Command Separation:** Each command has single, clear responsibility

### 🔄 **Next Implementation Step**

**Phase 5: Advanced Features & Optimization** - Next priority:
1. Enhanced position sizing algorithms (volatility-based, ATR-based)
2. Risk management improvements (portfolio heat, correlation checks)
3. Performance optimization (vectorized calculations, caching)
4. Advanced exit strategies (momentum-based, volatility-based exits)

## Implementation Priority

1. **Phase 1: Core Infrastructure** ✅ **COMPLETE**
   - ✅ Configuration and constants (6 new constants added)
   - ✅ Static stock list created (10 symbols + configurations)
   - ✅ IBClient methods for stocks (3 methods implemented)
   - ✅ Database schema (OpeningRange updated + Position model created + 6 new manager methods)

2. **Phase 2: Opening Range** ✅ **COMPLETE**
   - ✅ CalculateOpeningRangeCommand - Rewritten to use static STOCK_SYMBOLS
   - ✅ Range validation logic - Stock-specific min/max percentage checks
   - ✅ Database storage - Includes timeframe_minutes field
   - ✅ PrettyTable notifications - Clean Symbol/Range % format
   - ✅ StocksStrategyService - Added 4 new methods for ORB strategy

3. **Phase 3: Breakout Detection** ✅ **COMPLETE**
   - ✅ ORBSignalCommand - Detect breakouts, publish EVENT_TYPE_OPEN_POSITION
   - ✅ OpenPositionCommand - Execute trades based on signals
   - ✅ Clock-aligned monitoring - Check breakouts on proper intervals

4. **Phase 4: Order Execution & Position Management** ✅ **COMPLETE**
   - ✅ ManageStockPositionsCommand - Refactored for state transitions only (PENDING → OPEN → CLOSED)
   - ✅ MoveStopOrderCommand - Trailing stop implementation with CONFIG_TRAILING_STOP_RATIO
   - ✅ TimeBasedExitCommand - Stagnant position exits (>90 minutes)
   - ✅ EndOfDayExitCommand - EOD closure and daily reporting
   - ✅ Updated stocks.py with proper scheduling (30s, 1min, 1min, 12:50PM)
   - ✅ New EVENT_TYPE constants added to constants.py
   - ✅ All commands registered in orb_strategy_controller.py

5. **Phase 5: Advanced Features & Optimization** 🔄 **NEXT**
   - Enhanced position sizing algorithms
   - Risk management improvements
   - Performance optimization
   - Advanced exit strategies (momentum-based, volatility-based)

6. **Phase 6: Reporting & Analytics**
   - Performance tracking
   - Daily P&L reports
   - Strategy analytics

## Success Metrics

- Opening ranges calculated correctly
- Breakouts detected accurately
- Orders executed at expected prices
- Stop losses and take profits honored
- Trailing stops adjust properly
- All positions closed by EOD
- Risk per trade stays within limits
- Daily loss limits respected