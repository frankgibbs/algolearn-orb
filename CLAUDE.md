# Claude Development Guidelines

## Error Handling Pattern

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

### Check Server Status
```bash
curl http://192.168.86.30:8005/
```

### Notes
- All MCP tools use the `/mcp` endpoint with JSON-RPC 2.0 protocol
- The server runs inside the orb-stocks container
- Use port 8005 when calling from outside the Docker network
- Responses are in JSON format with either "result" or "error" fields