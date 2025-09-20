from src.core.observer import IObserver
from src.core.constants import *
from src.core.command_invoker import CommandInvoker
from src.stocks.commands.strategies.orb_strategy_command import ORBStrategyCommand
from src.stocks.commands.calculate_opening_range_command import CalculateOpeningRangeCommand
from src.stocks.commands.pre_market_scan_command import PreMarketScanCommand
from src.stocks.commands.manage_stock_positions_command import ManageStockPositionsCommand
from src.stocks.commands.stocks_connection_manager import StocksConnectionManager
from src import logger

class ORBStrategyController(IObserver):
    """Controller for ORB strategy - handles command registration and orchestration"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.subject = application_context.subject
        self.client = application_context.client
        self.state_manager = application_context.state_manager
        self.application_context = application_context

        # Subscribe to events
        self.state_manager.subject.subscribe(self)

        # Initialize command invoker
        self.command_invoker = CommandInvoker()

        # Register commands for stock trading events
        self._register_commands()

        logger.info("ORBStrategyController initialized with command registrations")

    def _register_commands(self):
        """Register all commands for stock trading events"""

        # Pre-market scanning command
        self.command_invoker.register_command(
            EVENT_TYPE_PRE_MARKET_SCAN,
            PreMarketScanCommand(self.application_context)
        )

        # Opening range calculation command
        self.command_invoker.register_command(
            EVENT_TYPE_CALCULATE_OPENING_RANGE,
            CalculateOpeningRangeCommand(self.application_context)
        )

        # ORB strategy command
        self.command_invoker.register_command(
            EVENT_TYPE_ORB_STRATEGY,
            ORBStrategyCommand(self.application_context)
        )

        # Position management command
        self.command_invoker.register_command(
            EVENT_TYPE_MANAGE_STOCK_POSITIONS,
            ManageStockPositionsCommand(self.application_context)
        )

        # Connection management command
        self.command_invoker.register_command(
            EVENT_TYPE_STOCKS_CONNECTION_CHECK,
            StocksConnectionManager(self.application_context)
        )

        logger.info("All stock trading commands registered successfully")

    def notify(self, observable, *args):
        """Handle events from observer pattern"""
        try:
            if not args or len(args) == 0:
                return

            event = args[0]
            event_type = event.get(FIELD_TYPE)

            # Route stock trading events to command invoker
            if event_type in [
                EVENT_TYPE_PRE_MARKET_SCAN,
                EVENT_TYPE_CALCULATE_OPENING_RANGE,
                EVENT_TYPE_ORB_STRATEGY,
                EVENT_TYPE_MANAGE_STOCK_POSITIONS,
                EVENT_TYPE_STOCKS_CONNECTION_CHECK,
                EVENT_TYPE_CLOSE_ALL_STOCK_POSITIONS
            ]:
                self.command_invoker.execute_command(event_type, event)

        except Exception as e:
            logger.error(f"Error in ORBStrategyController.notify: {e}")
            # Send error notification
            self.state_manager.sendTelegramMessage(f"🚨 ORB Controller Error: {e}")