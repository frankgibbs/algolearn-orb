# AlgoLearn ORB Strategy

Opening Range Breakout (ORB) stock trading strategy implementation using Interactive Brokers API.

## Project Overview

This is a production-ready ORB trading system that implements an automated Opening Range Breakout strategy for stocks. The system uses a **static stock list** (not pre-market scanning) and operates with the following workflow:

1. **Static Stock List**: Trades a predefined list of 10 liquid stocks (AAPL, MSFT, GOOGL, etc.)
2. **Opening Range Calculation**: Calculates opening ranges based on configurable timeframes (15m, 30m, or 60m)
3. **Breakout Detection**: Monitors for price breakouts above/below opening ranges using clock-aligned intervals
4. **Trade Execution**: Places entry orders with stop losses when breakout conditions are met
5. **Position Management**: Manages trailing stops, time-based exits, and end-of-day closure

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Interactive Brokers account with API access
- Telegram bot for notifications and commands (optional but recommended)

### Configuration
All configuration is done via docker-compose.yml environment variables:

```yaml
environment:
  - HOST=127.0.0.1                    # IB Gateway host
  - PORT=7497                         # IB Gateway port
  - IB_CLIENT_ID=80                   # Unique client ID
  - ACCOUNT=DU123456                  # IB account number
  - TELEGRAM_TOKEN=your_token_here    # Telegram bot token
  - TELEGRAM_CHAT_ID=your_chat_id     # Telegram chat ID
  - ORB_PERIOD_MINUTES=30             # Opening range period (15, 30, or 60)
  - RISK_PERCENTAGE=0.5               # Risk per trade (% of account)
  - MAX_POSITIONS=5                   # Max concurrent positions
  - MIN_PRICE=5.00                    # Minimum stock price filter
  - MAX_PRICE=100.00                  # Maximum stock price filter
  - MIN_VOLUME=100000                 # Minimum daily volume filter
```

## Telegram Integration

The system includes bidirectional Telegram integration for both notifications and interactive commands.

### Setting Up Telegram Bot
1. Create a bot via [@BotFather](https://t.me/botfather) on Telegram
2. Get your bot token from BotFather
3. Get your chat ID by messaging the bot and checking: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
4. Configure environment variables:
   - `TELEGRAM_TOKEN`: Your bot token from BotFather
   - `TELEGRAM_CHAT_ID`: Your chat ID for notifications

### Supported Commands
The bot responds to the following commands:

| Command | Description | Example |
|---------|-------------|---------|
| `/plot [symbol]` | Display candlestick chart for a stock | `/plot AAPL` |
| `/ranges` | Show today's opening ranges | `/ranges` |
| `/pnl` | Display P&L for open positions | `/pnl` |
| `/orders` | List all open orders from IB | `/orders` |

### Command Details

#### `/plot [symbol]`
- Generates a candlestick chart for the specified stock
- Uses the configured ORB_PERIOD_MINUTES for bar size
- Shows full trading day data
- Example: `/plot NVDA`

#### `/ranges`
- Displays all calculated opening ranges for the day
- Shows Symbol and Range % in a formatted table
- Only shows valid ranges that passed validation

#### `/pnl`
- Shows all open positions with unrealized P&L
- Displays Symbol, Quantity (+/- for long/short), and P&L
- Includes total P&L summary at the bottom

#### `/orders`
- Lists all open orders from Interactive Brokers
- Shows Order ID, Symbol, Quantity (+/- for buy/sell), and Order Type
- Useful for monitoring pending and active orders

### Notifications
Besides interactive commands, the bot automatically sends:
- Opening range calculations
- Trade signals and executions
- Position updates and P&L changes
- End-of-day summaries
- Error alerts and system status updates

### Deployment
```bash
# Update docker-compose.yml with your credentials
./deploy.sh

# View logs
docker-compose logs -f orb-stocks
```

## Architecture

### Core Components
- **Observer Pattern**: Event-driven architecture with state management
- **Command Pattern**: All trading operations are commands with centralized error handling
- **SQLAlchemy Models**: Database schema auto-creation
- **IB API Integration**: Real-time market data and order execution
- **Static Configuration**: Predefined stock list with stock-specific parameters

### Directory Structure
```
algolearn-orb/
├── src/
│   ├── core/              # Framework components
│   │   ├── ibclient.py    # IB API integration
│   │   ├── constants.py   # Configuration constants
│   │   └── command.py     # Command pattern base
│   └── stocks/            # ORB strategy implementation
│       ├── commands/      # Trading commands (9 commands)
│       ├── services/      # Business logic (3 services)
│       ├── models/        # Database models (4 models)
│       └── stocks_config.py # Static stock configuration
├── IBJts/                 # Interactive Brokers API
├── data/                  # SQLite database storage
├── stocks.py              # Main entry point
├── docker-compose.yml     # Service configuration
└── deploy.sh              # Deployment script
```

## Trading Schedule (Pacific Time)

The system operates on a precise schedule based on CONFIG_ORB_TIMEFRAME:

### Opening Range Calculation (Dynamic)
- **15-minute ORB**: Calculate at 6:45 AM PST (after 6:30-6:45 period)
- **30-minute ORB**: Calculate at 7:00 AM PST (after 6:30-7:00 period)
- **60-minute ORB**: Calculate at 7:30 AM PST (after 6:30-7:30 period)

### Breakout Monitoring (Clock-Aligned)
- **15-minute ORB**: Check at :00, :15, :30, :45 of each hour
- **30-minute ORB**: Check at :00, :30 of each hour
- **60-minute ORB**: Check at :00 of each hour

### Position Management (Continuous)
- **Position State Transitions**: Every 30 seconds (PENDING → OPEN → CLOSED)
- **Trailing Stop Management**: Every minute during market hours
- **Time-Based Exit Checks**: Every minute during market hours (>90 min stagnation)
- **End-of-Day Exit**: 12:50 PM PST (closes all remaining positions)

### Connection Management
- **Smart Connection Check**: Every 5 minutes
- **Market Hours**: 6:30 AM - 1:00 PM PST

## Commands Documentation

The system uses 9 specialized commands for different trading operations:

### Core ORB Strategy Commands

#### 1. CalculateOpeningRangeCommand
**File**: `src/stocks/commands/calculate_opening_range_command.py`
**Responsibility**: Calculate opening ranges for all stocks in static list
**Execution**: Dynamic timing based on CONFIG_ORB_TIMEFRAME
- Fetches single bar data matching timeframe from IB API
- Validates range percentage against stock-specific min/max thresholds
- Stores only valid ranges in database
- Sends PrettyTable notification with range percentages

#### 2. ORBSignalCommand
**File**: `src/stocks/commands/strategies/orb_signal_command.py`
**Responsibility**: Detect breakout signals and publish position opening events
**Execution**: Clock-aligned intervals based on CONFIG_ORB_TIMEFRAME
- Analyzes previous completed candle vs opening range
- Checks position limits before signal generation
- Publishes EVENT_TYPE_OPEN_POSITION events (no direct execution)
- Calculates position size based on account risk percentage

#### 3. OpenPositionCommand
**File**: `src/stocks/commands/open_position_command.py`
**Responsibility**: Execute trades based on position signals (strategy-agnostic)
**Execution**: Event-driven (listens for EVENT_TYPE_OPEN_POSITION)
- Validates 10 required fields in event data
- Checks position limits and margin requirements
- Places entry and stop orders via IBClient
- Creates Position records in database

### Position Management Commands

#### 4. ManageStockPositionsCommand
**File**: `src/stocks/commands/manage_stock_positions_command.py`
**Responsibility**: Monitor position state transitions (PENDING → OPEN → CLOSED)
**Execution**: Every 30 seconds
- Checks pending positions for order fills
- Transitions filled orders to OPEN status
- Checks open positions for stop order fills
- Transitions closed positions with exit details and P&L

#### 5. MoveStopOrderCommand
**File**: `src/stocks/commands/move_stop_order_command.py`
**Responsibility**: Handle trailing stop order modifications
**Execution**: Every minute during market hours
- Activates trailing when current price >= take_profit_price
- Moves stops progressively as price advances favorably
- Uses CONFIG_TRAILING_STOP_RATIO (0.5x of range)
- Modifies existing stop orders via IBClient

#### 6. TimeBasedExitCommand
**File**: `src/stocks/commands/time_based_exit_command.py`
**Responsibility**: Handle time-based exits for stagnant positions
**Execution**: Every minute during market hours
- Identifies positions open >90 minutes with <25% range movement
- Closes stagnant positions with market orders
- Updates exit_reason = "TIME_EXIT_STAGNANT"
- Cancels existing stop orders before closure

#### 7. EndOfDayExitCommand
**File**: `src/stocks/commands/end_of_day_exit_command.py`
**Responsibility**: Handle end-of-day position closure and daily reporting
**Execution**: Daily at 12:50 PM PST
- Closes all remaining positions with market orders
- Generates comprehensive daily P&L report with PrettyTable
- Includes win rate, avg win/loss, detailed trade breakdown
- Updates exit_reason = "EOD_EXIT"

### Supporting Commands

#### 8. PreMarketScanCommand
**File**: `src/stocks/commands/pre_market_scan_command.py`
**Responsibility**: Pre-market stock scanning (legacy - not used in static list mode)
**Execution**: 5:30 AM PST (disabled in current implementation)

#### 9. StocksConnectionManager
**File**: `src/stocks/commands/stocks_connection_manager.py`
**Responsibility**: Monitor and maintain IB Gateway connection health
**Execution**: Every 5 minutes

## Services Documentation

The system uses 3 core services for business logic:

### 1. StocksStrategyService
**File**: `src/stocks/services/stocks_strategy_service.py`
**Responsibility**: Core strategy logic and database operations
**Key Methods**:
- `calculate_range()` - Extract OHLC from IB bar data
- `save_opening_range()` - Store range with timeframe_minutes
- `get_opening_range()` - Fetch range for breakout analysis
- `get_open_positions_count()` - Position limit checking
- `calculate_position_parameters()` - Position sizing logic

### 2. StocksScannerService
**File**: `src/stocks/services/stocks_scanner_service.py`
**Responsibility**: Stock scanning and filtering (legacy - not used in static mode)

### 3. Additional Managers
- **StocksDatabaseManager**: Database operations and queries
- **StocksTradeManager**: Trade execution coordination
- **StocksTelegramManager**: Notification system

## Database Schema

SQLAlchemy automatically creates these tables:

### opening_ranges
```sql
- id (Primary Key)
- symbol (String) - Stock symbol
- date (Date) - Trading date
- timeframe_minutes (Integer) - 15, 30, or 60 minutes
- range_high (Float) - Opening range high
- range_low (Float) - Opening range low
- range_size (Float) - Range size in dollars
- range_size_pct (Float) - Range size as percentage
- created_at (DateTime)
```

### positions
```sql
- id (Primary Key) - THIS IS the parent order ID
- stop_order_id (Integer) - Child stop order ID
- opening_range_id (Foreign Key) - Links to opening_ranges
- symbol (String) - Stock symbol
- direction (String) - 'LONG' or 'SHORT'
- entry_time (DateTime)
- entry_price (Float)
- shares (Integer)
- stop_loss_price (Float) - Original stop price
- take_profit_price (Float) - Monitored level (NOT an order)
- stop_moved (Boolean) - True if stop has been modified
- trailing_stop_price (Float) - Current stop price if moved
- range_size (Float) - For trailing calculations
- current_price (Float)
- unrealized_pnl (Float)
- status (String) - 'PENDING', 'OPEN', 'CLOSED'
- exit_time (DateTime)
- exit_price (Float)
- exit_reason (String)
- realized_pnl (Float)
- created_at (DateTime)
- updated_at (DateTime)
```

### stock_candidates (Legacy)
- Pre-market scan results (not used in static list mode)

### trade_decisions (Legacy)
- Audit trail of trading decisions (not used in current implementation)

## Static Stock Configuration

The system trades a predefined list of 10 liquid stocks with stock-specific parameters:

### Stock List
```python
STOCK_SYMBOLS = [
    "AAPL",  # Apple Inc.
    "MSFT",  # Microsoft Corporation
    "GOOGL", # Alphabet Inc. Class A
    "AMZN",  # Amazon.com Inc.
    "NVDA",  # NVIDIA Corporation
    "TSLA",  # Tesla Inc.
    "META",  # Meta Platforms Inc.
    "AMD",   # Advanced Micro Devices Inc.
    "SPY",   # SPDR S&P 500 ETF Trust
    "QQQ",   # Invesco QQQ Trust
]
```

### Stock-Specific Configurations
```python
STOCK_CONFIGS = {
    "TSLA": {"min_range_pct": 1.0, "max_range_pct": 5.0},  # More volatile
    "NVDA": {"min_range_pct": 0.8, "max_range_pct": 4.0},  # High volatility
    "AMD":  {"min_range_pct": 0.8, "max_range_pct": 4.0},  # High volatility
    "SPY":  {"min_range_pct": 0.3, "max_range_pct": 2.0},  # Less volatile ETF
    "QQQ":  {"min_range_pct": 0.4, "max_range_pct": 2.5},  # Moderate volatility
}

# Default for stocks not listed above
DEFAULT_STOCK_CONFIG = {
    "min_range_pct": 0.5,  # Default minimum range as % of price
    "max_range_pct": 3.0   # Default maximum range as % of price
}
```

## ORB Strategy Rules

### Entry Conditions
- **Opening Range**: First 15, 30, or 60 minutes after market open (configurable)
- **Breakout Signal**: Previous candle closes above range high (long) or below range low (short)
- **Range Validation**: Range must be within stock-specific min/max percentage bounds

### Risk Management
- **Stop Loss**: Range midpoint - actual IB stop order
- **Take Profit**: 1.5x opening range size from entry - monitored price level (not an order)
- **Trailing Stop**: After TP hit, trail at 0.5x opening range size - modifies existing stop order
- **Position Sizing**: Based on account risk percentage and price difference
- **Max Positions**: Configurable limit on concurrent positions

### Exit Conditions
- Stop loss hit (automatic via IB)
- Take profit hit → switches to trailing stop mode
- Time-based exit (position stagnant >90 minutes)
- End of day (12:50 PM PST) - all remaining positions closed

## Configuration Constants

### Required Environment Variables
All configuration is done via environment variables that map to these constants:

#### Core IB Configuration
```python
CONFIG_HOST = "host"                    # IB Gateway host
CONFIG_PORT = "port"                    # IB Gateway port
CONFIG_CLIENT_ID = "client_id"          # Unique client ID
CONFIG_ACCOUNT = "account"              # IB account number
```

#### ORB Strategy Configuration
```python
CONFIG_ORB_TIMEFRAME = "orb_timeframe"           # 15, 30, or 60 minutes
CONFIG_MIN_RANGE_PCT = "min_range_pct"           # Minimum range as % of price
CONFIG_MAX_RANGE_PCT = "max_range_pct"           # Maximum range as % of price
CONFIG_TRAILING_STOP_RATIO = "trailing_stop_ratio"  # 0.5x of range
CONFIG_TAKE_PROFIT_RATIO = "take_profit_ratio"      # 1.5x of range
```

#### Risk Management Configuration
```python
CONFIG_RISK_PERCENTAGE = "risk_percentage"      # Risk per trade (% of account)
CONFIG_MAX_POSITIONS = "max_positions"          # Max concurrent positions
```

#### Stock Filtering Configuration
```python
CONFIG_MIN_PRICE = "min_price"                  # Minimum stock price
CONFIG_MAX_PRICE = "max_price"                  # Maximum stock price
CONFIG_MIN_VOLUME = "min_volume"                # Minimum daily volume
```

### Default Values
```yaml
ORB_PERIOD_MINUTES: 30        # 30-minute opening range
RISK_PERCENTAGE: 0.5          # 0.5% risk per trade
MAX_POSITIONS: 5              # Maximum 5 concurrent positions
MIN_PRICE: 5.00              # $5 minimum stock price
MAX_PRICE: 100.00            # $100 maximum stock price
MIN_VOLUME: 100000           # 100K minimum daily volume
```

## Error Handling

The system follows a strict error handling pattern documented in `CLAUDE.md`:

### Command Pattern
- **Commands**: Raise descriptive exceptions on failures (no try/catch)
- **Services**: Raise exceptions instead of returning None/False
- **IBClient**: Raises TimeoutError, RuntimeError, ValueError with context
- **CommandInvoker**: Catches all exceptions, logs with stack trace, sends notifications

### Exception Propagation
```python
# Correct Pattern - Commands let exceptions propagate
class ORBSignalCommand(Command):
    def execute(self, event):
        # No try/catch - let exceptions propagate
        opening_range = strategy_service.get_opening_range(symbol, date)
        bars = ib_client.get_stock_bars(symbol, timeframe)

        # CommandInvoker handles all exceptions automatically
```

### Error Recovery
- **No silent failures**: All errors are logged and reported via Telegram
- **Graceful degradation**: Individual stock failures don't stop other stocks
- **Connection recovery**: Automatic reconnection on IB Gateway disconnects
- **Position safety**: All positions tracked in database for recovery

## Implementation Status

### ✅ Completed Features
- [x] Complete ORB strategy implementation with 9 commands
- [x] Static stock list with stock-specific configurations
- [x] Opening range calculation with timeframe support (15m/30m/60m)
- [x] Breakout detection with clock-aligned monitoring
- [x] Position management with state transitions
- [x] Trailing stop implementation
- [x] Time-based and end-of-day exits
- [x] Comprehensive database schema
- [x] IB API integration with all required methods
- [x] Event-driven architecture with Observer pattern
- [x] Telegram notification system
- [x] Docker containerization
- [x] Error handling per CLAUDE.md pattern
- [x] Scheduling system with market hours validation

### Risk Controls
- **Pre-Trade Validation**: Valid opening range, position limits, range bounds
- **Real-Time Monitoring**: Position state tracking, P&L calculation
- **Automatic Exits**: Stop losses, trailing stops, time-based exits, EOD closure
- **Error Handling**: Exception propagation with notification system

## Testing

Before production use:

1. **Paper Trading**: Test with IB paper trading account
2. **Configuration Validation**: Verify all environment variables are set
3. **Range Calculation**: Validate opening range accuracy
4. **Breakout Detection**: Test signal generation on historical data
5. **Order Execution**: Verify entry and stop order placement
6. **Position Management**: Test state transitions and exits
7. **Risk Controls**: Validate position limits and stop losses

## Monitoring

- **Logs**: `docker-compose logs -f orb-stocks`
- **Database**: SQLite file in `./data/` volume
- **Telegram Bot**: Real-time notifications and interactive commands (see [Telegram Integration](#telegram-integration))
- **Health Checks**: Connection status and system health monitoring
- **P&L Tracking**: Real-time unrealized P&L and daily reports

## Troubleshooting

### Common Issues
1. **IB Gateway Connection**: Verify HOST, PORT, and ACCOUNT settings
2. **Configuration Errors**: Check all required environment variables are set
3. **Range Validation**: Stocks may be skipped if ranges are outside min/max bounds
4. **Position Limits**: Signals ignored if MAX_POSITIONS reached
5. **Market Hours**: Commands only execute during valid trading hours

### Log Analysis
```bash
# View all logs
docker-compose logs -f orb-stocks

# Search for specific errors
docker-compose logs orb-stocks | grep ERROR

# Check position updates
docker-compose logs orb-stocks | grep "Position"
```

## Support

For questions or issues:
- Check logs for detailed error information
- Verify IB Gateway connection and permissions
- Ensure all environment variables are properly configured
- Test with paper trading account before live trading
- Monitor Telegram notifications for real-time system status