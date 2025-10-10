# Claude Development Guidelines

## Error Handling Pattern

### Configuration Values - NO SILENT FALLBACKS
- **NEVER** use `or` operator for silent config defaults (e.g., `get_config_value(CONFIG_X) or 20`)
- **DO** raise ValueError when required configs are missing
- **DO** validate config values are reasonable (not None, not negative for counts, etc.)
- **DO** include the missing config name in the exception message

#### Wrong Pattern - Silent Fallback:
```python
# NEVER DO THIS - hides missing configuration
lookback_bars = self.state_manager.get_config_value(CONFIG_ORB_VOLUME_LOOKBACK) or 20
risk_pct = self.state_manager.get_config_value(CONFIG_RISK_PERCENTAGE) or 1.0
```

#### Correct Pattern - Explicit Validation:
```python
# DO THIS - fail fast with clear error
lookback_bars = self.state_manager.get_config_value(CONFIG_ORB_VOLUME_LOOKBACK)
if lookback_bars is None:
    raise ValueError("CONFIG_ORB_VOLUME_LOOKBACK is REQUIRED")

risk_pct = self.state_manager.get_config_value(CONFIG_RISK_PERCENTAGE)
if risk_pct is None or risk_pct <= 0:
    raise ValueError("CONFIG_RISK_PERCENTAGE is REQUIRED and must be positive")
```

### Commands and Services
- **DO NOT** use try/catch blocks in commands unless you're handling a specific recoverable error
- **DO** raise descriptive exceptions when operations fail
- **DO** let exceptions propagate to CommandInvoker

### IBClient Methods
- **DO** raise exceptions on failures (TimeoutError, RuntimeError, ValueError)
- **DO NOT** return None/False on errors - raise exceptions instead
- **DO** include context in exception messages

### Example - Correct Pattern:

#### In Command - NO try/catch needed
```python
class ORBStrategyCommand(Command):
    def execute(self, event):
        # Just call the method, let exceptions propagate
        result = self.client.place_stock_entry_with_stop(
            symbol="AAPL",
            action="BUY",
            quantity=100,
            entry_price=150.00,
            stop_price=149.00
        )

        # Continue with success path
        self.database_manager.save_position(result)
```

#### In IBClient - Raise on errors
```python
def place_stock_entry_with_stop(self, ...):
    if not confirmation:
        raise RuntimeError(f"Order rejected for {symbol}")

    if timeout:
        raise TimeoutError(f"Order confirmation timeout for {symbol}")

    return result  # Only return on success
```

### CommandInvoker Handles Everything:
- Catches all exceptions
- Logs with stack trace
- Sends Telegram notifications
- Continues processing other commands

This pattern ensures:
- Clean separation of concerns
- Consistent error handling
- No missed errors
- Proper notifications to user

## MCP Tool Usage with curl

### Docker Infrastructure
- **Active Docker Context**: tensor (ssh://frankg@192.168.86.30)
- **Container**: orb-stocks
- **Port Mapping**: External 8005 → Internal 8003
- **Base URL**: http://192.168.86.30:8005

### Available MCP Tools

#### 1. Run Pre-Market Scan
```bash
curl -X POST http://192.168.86.30:8005/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "run_pre_market_scan",
      "arguments": {
        "min_price": 5.0,
        "max_price": 100.0,
        "min_volume": 100000,
        "min_pre_market_change": 2.0,
        "max_results": 50
      }
    }
  }'
```

#### 2. Get Current Candidates
```bash
curl -X POST http://192.168.86.30:8005/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_current_candidates",
      "arguments": {
        "limit": 25
      }
    }
  }'
```

#### 3. Get Scanner Types
```bash
curl -X POST http://192.168.86.30:8005/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_scanner_types",
      "arguments": {}
    }
  }'
```

#### 4. Get Opening Ranges
```bash
curl -X POST http://192.168.86.30:8005/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_opening_ranges",
      "arguments": {
        "date": "2025-09-25",
        "days_back": 3,
        "include_all": false
      }
    }
  }'
```

#### 5. Get All Positions
```bash
curl -X POST http://192.168.86.30:8005/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_all_positions",
      "arguments": {
        "days_back": 1
      }
    }
  }'
```

##### Get all positions for specific symbol:
```bash
curl -X POST http://192.168.86.30:8005/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_all_positions",
      "arguments": {
        "symbol": "AAPL",
        "days_back": 7
      }
    }
  }'
```

### Check Server Status
```bash
curl http://192.168.86.30:8005/
```

### Notes
- All MCP tools use the `/mcp` endpoint with JSON-RPC 2.0 protocol
- The server runs inside the orb-stocks container
- Use port 8005 when calling from outside the Docker network
- Responses are in JSON format with either "result" or "error" fields

## Volatility Analysis & Options Strategy Selection

### Framework (Based on Natenberg's "Option Volatility and Pricing")

This system implements a complete volatility-based options strategy selection framework using real-time Interactive Brokers data.

### Key Concepts

1. **Implied Volatility (IV)**: Market's expectation of future volatility, derived from ATM option prices
2. **Historical Volatility (HV)**: Realized volatility calculated from price returns: `std(ln(P[t]/P[t-1])) * sqrt(252)`
3. **IV/HV Ratio**: Primary metric for determining if options are overpriced or underpriced
   - **< 0.85**: Options underpriced → BUY volatility (long options, spreads)
   - **> 1.25**: Options overpriced → SELL volatility (short premium strategies)
   - **0.85-1.25**: NEUTRAL → Use spread strategies
4. **Term Structure**: IV across multiple expirations
   - **Upward slope**: Back month IV > front month (normal contango)
   - **Inverted**: Front month IV > back month (near-term uncertainty/event)

### Available Volatility MCP Tools

#### 1. Complete Volatility Analysis
```bash
curl -X POST http://192.168.86.30:8005/mcp -H "Content-Type: application/json" -d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "analyze_volatility",
    "arguments": {
      "symbol": "AAPL"
    }
  }
}'
```

**Returns:**
- Current ATM IV (call/put/average)
- Historical volatility (10, 20, 30, 60 day)
- IV/HV ratio
- Volatility term structure (30, 60, 90 days)
- Trading signal (BUY_VOLATILITY, SELL_VOLATILITY, NEUTRAL)

#### 2. Get Real Option Quotes
```bash
curl -X POST http://192.168.86.30:8005/mcp -H "Content-Type: application/json" -d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_option_quote",
    "arguments": {
      "symbol": "AAPL",
      "expiry": "20251107",
      "strike": 250,
      "right": "P"
    }
  }
}'
```

**Returns:**
- Bid/ask/mid prices
- Greeks (delta, gamma, theta, vega, IV)
- Underlying price
- Last trade price

#### 3. Get Stock Bars (Historical Prices)
```bash
curl -X POST http://192.168.86.30:8005/mcp -H "Content-Type: application/json" -d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_stock_bars",
    "arguments": {
      "symbol": "AAPL",
      "duration": "252 D",
      "bar_size": "1 day"
    }
  }
}'
```

### Standard Analysis Workflow

When asked to analyze a symbol for options strategies:

#### Step 1: Run Volatility Analysis
```bash
analyze_volatility(symbol="XYZ")
```

Review the output to determine:
- Current IV level (absolute volatility)
- IV/HV ratio (relative valuation)
- Term structure slope (calendar opportunities)
- Trading signal

#### Step 2: Analyze Price Trend (REQUIRED)
```bash
get_stock_bars(symbol="XYZ", duration="90 D", bar_size="1 day")
```

**CRITICAL:** Always analyze recent price action before selecting strategy. Review last 20-30 days:

**Trend Analysis:**
- Identify trend direction (uptrend, downtrend, sideways)
- Check for failed breakouts or reversals
- Locate key support/resistance levels
- Assess recent volume patterns
- Note any gaps or significant price moves

**Strategy Alignment:**
- **Bull Put Spread**: Requires neutral-to-bullish trend, avoid during downtrends
- **Bear Call Spread**: Requires neutral-to-bearish trend, avoid during uptrends
- **Iron Condor**: Best in sideways/range-bound markets
- **Vertical Spreads**: Must align with directional bias

**Red Flags:**
- ❌ Failed breakout followed by reversal
- ❌ Multiple consecutive down days on high volume (for bullish strategies)
- ❌ Multiple consecutive up days on high volume (for bearish strategies)
- ❌ Breaking below key support (for bullish strategies)
- ❌ Breaking above key resistance (for bearish strategies)

**Example: BA Analysis**
```
Recent: Oct 8 high $225 → Oct 10 low $210 (-6.6% in 2 days)
Assessment: Failed breakout, bearish short-term
Conclusion: AVOID bull put spreads - wait for stabilization
```

#### Step 3: Select Appropriate Strategies Based on Signal + Trend

**SELL_VOLATILITY (IV/HV > 1.25):**
- Iron Condor (defined risk, premium collection) - requires sideways trend
- Bull Put Spread - requires neutral-to-bullish trend
- Bear Call Spread - requires neutral-to-bearish trend
- Iron Butterfly (max premium, tight profit zone) - requires sideways trend

**BUY_VOLATILITY (IV/HV < 0.85):**
- Long Straddle/Strangle - neutral on direction
- Calendar spreads (if term structure supports) - check trend alignment
- Vertical spreads (directional bias) - MUST confirm trend supports direction

**NEUTRAL (0.85 < IV/HV < 1.25):**
- Iron Condor (balanced approach) - requires sideways trend
- Vertical spreads with directional view - MUST confirm trend supports direction

#### Step 4: Get Real Market Prices
Use `get_option_quote` to fetch actual bid/ask for all legs of the strategy.

**IMPORTANT:** Always use real market prices - never estimate or guess option prices.

#### Step 5: Calculate Strategy Metrics

For each strategy, calculate:
- **Premium collected**: Net credit received
- **Max risk**: Maximum possible loss
- **ROI**: (Premium / Max Risk) × 100
- **Breakeven points**: Strike ± premium for spreads
- **Profit zone**: Distance between breakevens as % of underlying price
- **Days to expiration**: Time value decay

#### Step 6: Compare Strategies & Recommend

Provide analysis comparing:
- Risk-defined vs undefined risk
- ROI vs probability of profit
- Capital efficiency
- Management complexity
- **Trend alignment**: Confirm strategy direction matches price action

### Strategy Calculation Examples

#### Iron Condor (XYZ @ $100, target 5-wide spreads)
```
Bull Put Spread:
- Sell 95P @ $1.50 (bid)
- Buy 90P @ $0.75 (ask)
- Credit: $0.75

Bear Call Spread:
- Sell 105C @ $1.40 (bid)
- Buy 110C @ $0.70 (ask)
- Credit: $0.70

Total credit: $1.45 ($145)
Max risk: $355 ($500 - $145)
ROI: 40.8%
Breakevens: $93.55 / $106.45
Profit zone: $12.90 (12.9%)
```

#### Iron Butterfly (XYZ @ $100, 10-wide wings)
```
- Sell 100P @ $3.50 (bid)
- Sell 100C @ $3.60 (bid)
- Buy 90P @ $1.20 (ask)
- Buy 110C @ $1.30 (ask)

Total credit: $4.60 ($460)
Max risk: $540 ($1,000 - $460)
ROI: 85.2%
Breakevens: $95.40 / $104.60
Profit zone: $9.20 (9.2%)
```

### Key Guidelines

1. **Always use real bid/ask prices** - sell at bid, buy at ask
2. **Calculate actual ROI** - don't estimate
3. **Consider probability of profit** based on profit zone width
4. **Account for liquidity** - tight bid/ask spreads are crucial
5. **Factor in commission costs** for multi-leg strategies
6. **Analyze price trend before selecting strategy** - NEVER place bullish spreads during downtrends or bearish spreads during uptrends
7. **Use volatility analysis to guide strategy selection** - don't trade against the volatility regime (high IV = sell premium, low IV = buy options)

### Service Layer

The `VolatilityService` (`src/stocks/services/volatility_service.py`) provides:
- `get_historical_prices()` - OHLC bars with IB native format
- `calculate_historical_volatility()` - Natenberg formula for HV
- `get_current_atm_iv()` - Real-time ATM implied volatility
- `get_volatility_term_structure()` - IV across expirations
- `analyze_complete_volatility()` - Complete analysis with signal

All methods use real-time IB data (no caching/storage currently).