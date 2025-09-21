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