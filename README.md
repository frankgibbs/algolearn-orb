# AlgoLearn ORB Strategy

Opening Range Breakout (ORB) stock trading strategy implementation using Interactive Brokers API.

## Project Overview

This is a standalone ORB trading system extracted from the algolearn-forex project, specifically designed for stock trading. The system implements an automated Opening Range Breakout strategy that:

1. Scans pre-market for stock candidates
2. Calculates opening ranges during market open
3. Monitors for breakouts throughout the trading day
4. Executes trades when conditions are met
5. Manages positions with stop losses and take profits

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Interactive Brokers account with API access
- Telegram bot for notifications (optional)

### Configuration
All configuration is done via docker-compose.yml environment variables:

```yaml
environment:
  - HOST=127.0.0.1           # IB Gateway host
  - PORT=7497                # IB Gateway port
  - IB_CLIENT_ID=80          # Unique client ID
  - ACCOUNT=DU123456         # IB account number
  - TELEGRAM_TOKEN=your_token_here
  - TELEGRAM_CHAT_ID=your_chat_id
  - ORB_PERIOD_MINUTES=30    # Opening range period
  - RISK_PERCENTAGE=0.5      # Risk per trade (%)
  - MAX_POSITIONS=5          # Max concurrent positions
  - MIN_PRICE=5.00          # Minimum stock price
  - MAX_PRICE=100.00        # Maximum stock price
  - MIN_VOLUME=100000       # Minimum daily volume
```

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

### Directory Structure
```
algolearn-orb/
├── src/
│   ├── core/              # Framework components
│   └── stocks/            # ORB strategy implementation
│       ├── commands/      # Trading commands
│       ├── services/      # Business logic
│       └── models/        # Database models
├── IBJts/                 # Interactive Brokers API
├── data/                  # SQLite database storage
├── stocks.py              # Main entry point
├── docker-compose.yml     # Service configuration
└── deploy.sh              # Deployment script
```

### Trading Schedule (Pacific Time)
- **5:30 AM**: Pre-market scan for candidates
- **7:00 AM**: Calculate opening ranges
- **7:00-12:00 PM**: ORB strategy checks (every 30 min)
- **Every minute**: Position management
- **12:50 PM**: Close all positions

## Database Schema

SQLAlchemy automatically creates these tables:

### opening_ranges
- Stores daily opening range data (high, low, size, size%)
- Used for breakout detection

### stock_candidates
- Pre-market scan results
- Selection criteria and ranking

### trade_decisions
- Audit trail of all trading decisions
- Action, reason, confidence, execution status

### trades (extends existing)
- Actual trade records with P&L
- Links to opening ranges and breakout data

## Implementation Status

### ✅ Completed
- [x] Project structure and Docker setup
- [x] Core framework (observer, command patterns)
- [x] Database models and schema
- [x] ORB strategy controller and command registration
- [x] Scheduling system for trading activities
- [x] Telegram integration framework
- [x] Basic position management structure

### 🚧 TODO - Critical Implementations Needed

#### Data Integration
- [ ] **Historical Data Fetching**: Implement IB API calls to get opening range data
- [ ] **Real-time Price Data**: Get current market prices for breakout detection
- [ ] **Contract Resolution**: Convert stock symbols to IB contract objects

#### Strategy Logic
- [ ] **Breakout Detection**: Complete logic to identify range breakouts
- [ ] **Market Conditions Validation**: Check market internals before trading
- [ ] **Trade Parameter Calculation**: Calculate entry, stop loss, take profit prices

#### Execution Engine
- [ ] **Order Placement**: Execute actual buy/sell orders via IB API
- [ ] **Position Tracking**: Get current positions from IB account
- [ ] **P&L Monitoring**: Real-time position updates and P&L calculation

#### Risk Management
- [ ] **Stop Loss Management**: Implement trailing stops and exit logic
- [ ] **Position Sizing**: Calculate share quantities based on risk percentage
- [ ] **Daily Loss Limits**: Circuit breakers for risk control

#### Scanner Integration
- [ ] **Pre-market Scanner**: Implement actual stock screening logic
- [ ] **Volume/Price Filters**: Apply filtering criteria to candidates
- [ ] **Candidate Selection**: Ranking and selection algorithms

### Key Files Needing Implementation

#### `src/stocks/services/stocks_strategy_service.py`
- Lines 158, 185, 225, 242, 267: Core strategy logic

#### `src/stocks/commands/strategies/orb_strategy_command.py`
- Lines 86, 96, 137, 164: Market data and execution

#### `src/stocks/commands/manage_stock_positions_command.py`
- Lines 32, 65, 81-83, 123, 148-149: Position management

#### `src/stocks/commands/calculate_opening_range_command.py`
- Lines 84, 95: Historical data fetching

## Testing

Before production use:

1. **Paper Trading**: Test with IB paper trading account
2. **Data Validation**: Verify historical data accuracy
3. **Risk Controls**: Test stop losses and position limits
4. **Error Handling**: Validate connection failures and recovery
5. **Performance**: Monitor system performance under load

## Monitoring

- **Logs**: `docker-compose logs -f orb-stocks`
- **Database**: SQLite file in `./data/` volume
- **Telegram**: Real-time notifications of trades and errors
- **Health Checks**: Connection and system status monitoring

## Next Steps

1. Implement critical TODO items listed above
2. Add comprehensive error handling and logging
3. Create backtesting framework
4. Add performance monitoring and alerts
5. Implement additional risk management features

## Support

For questions or issues:
- Check logs for error details
- Verify IB Gateway connection and permissions
- Ensure all environment variables are properly set
- Test with paper trading account first