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