from src.core.command import Command
from src.core.constants import *
from src.core.ibclient import IBClient
from src.stocks.stocks_database_manager import StocksDatabaseManager
from src.stocks.services.stocks_strategy_service import StocksStrategyService
from src import logger

class OpenPositionCommand(Command):
    """
    Strategy-agnostic position opening command
    Listens for EVENT_TYPE_OPEN_POSITION events and executes trades
    """

    def execute(self, event):
        """
        Execute position opening based on event data

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None or invalid
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.info("Executing position opening command")

        # Extract event data
        event_data = event.get(FIELD_DATA)
        if not event_data:
            raise ValueError("event data is REQUIRED")

        # Validate the position request
        self._validate_position_request(event_data)

        symbol = event_data['symbol']
        action = event_data['action']
        quantity = event_data['quantity']

        logger.info(f"Processing position request: {action} {quantity} {symbol}")

        # Check position limits
        if not self._check_position_limits():
            logger.info(f"Position limits reached, skipping {symbol}")
            return

        # TODO: Add margin requirement check when pattern is ready
        # account_value = self._get_account_value()
        # required_capital = quantity * entry_price
        # if not self._check_margin_requirements(required_capital, account_value):
        #     logger.warning(f"Insufficient margin for {symbol}")
        #     return

        # Initialize clients
        # Use the IBClient instance from application context (maintains connection)
        ib_client = self.application_context.client
        database_manager = StocksDatabaseManager(self.application_context)

        # Execute the trade
        order_result = ib_client.place_stock_entry_with_stop(
            symbol=event_data['symbol'],
            action=event_data['action'],
            quantity=event_data['quantity'],
            entry_price=event_data['entry_price'],
            stop_price=event_data['stop_loss']
        )

        logger.info(f"Order placed successfully: Parent ID {order_result['parent_order_id']}, "
                   f"Stop ID {order_result['stop_order_id']}")

        # Create position record in database
        position = database_manager.create_position(
            order_result=order_result,
            opening_range_id=event_data['opening_range_id'],
            take_profit_price=event_data['take_profit'],
            range_size=event_data['range_size']
        )

        logger.info(f"Position created in database: {position}")

        # Send confirmation notification
        self._send_confirmation_notification(event_data, order_result)

        logger.info(f"Position opening complete for {symbol}")

    def _validate_position_request(self, event_data):
        """
        Validate that event data contains all required fields

        Args:
            event_data: Position request data (required)

        Raises:
            ValueError: If required fields are missing or invalid
        """
        if not event_data:
            raise ValueError("event_data is REQUIRED")

        required_fields = [
            'strategy', 'symbol', 'action', 'quantity', 'entry_price',
            'stop_loss', 'take_profit', 'range_size', 'opening_range_id', 'reason'
        ]

        for field in required_fields:
            if field not in event_data:
                raise ValueError(f"Required field '{field}' missing from event data")

        # Validate field values
        if event_data['action'] not in ['BUY', 'SELL']:
            raise ValueError("action must be 'BUY' or 'SELL'")

        if event_data['quantity'] <= 0:
            raise ValueError("quantity must be positive")

        if event_data['entry_price'] <= 0:
            raise ValueError("entry_price must be positive")

        if event_data['stop_loss'] <= 0:
            raise ValueError("stop_loss must be positive")

        if event_data['take_profit'] <= 0:
            raise ValueError("take_profit must be positive")

        if event_data['range_size'] <= 0:
            raise ValueError("range_size must be positive")

        logger.debug(f"Position request validation passed for {event_data['symbol']}")

    def _check_position_limits(self):
        """
        Check if we can open new positions based on configured limits

        Returns:
            Boolean indicating if new positions can be opened
        """
        max_positions = self.state_manager.get_config_value(CONFIG_MAX_POSITIONS)
        if max_positions is None:
            raise ValueError("CONFIG_MAX_POSITIONS not configured")

        # Get current open position count
        strategy_service = StocksStrategyService(self.application_context)
        current_positions = strategy_service.get_open_positions_count()

        logger.debug(f"Current positions: {current_positions}, Max allowed: {max_positions}")

        return current_positions < max_positions

    def _send_confirmation_notification(self, event_data, order_result):
        """
        Send Telegram notification confirming position opening

        Args:
            event_data: Original position request data
            order_result: Result from IBClient order placement
        """
        symbol = event_data['symbol']
        action = event_data['action']
        quantity = event_data['quantity']
        entry_price = event_data['entry_price']
        stop_loss = event_data['stop_loss']
        take_profit = event_data['take_profit']
        strategy = event_data['strategy']
        reason = event_data['reason']

        message = (
            f"✅ {strategy} Position Opened\n"
            f"Symbol: {symbol}\n"
            f"Action: {action} {quantity} shares\n"
            f"Entry: ${entry_price:.2f}\n"
            f"Stop: ${stop_loss:.2f}\n"
            f"Target: ${take_profit:.2f}\n"
            f"Order IDs: {order_result['parent_order_id']}/{order_result['stop_order_id']}\n"
            f"Reason: {reason}"
        )

        self.state_manager.sendTelegramMessage(message)
        logger.info(f"Confirmation notification sent for {symbol}")