from src.core.observer import IObserver
from src.core.constants import *
from src.core.command_invoker import CommandInvoker

from src.stocks.commands.pre_market_scan_command import PreMarketScanCommand
from src.stocks.commands.calculate_opening_range_command import CalculateOpeningRangeCommand
from src.stocks.commands.open_position_command import OpenPositionCommand
from src.stocks.commands.manage_stock_positions_command import ManageStockPositionsCommand
from src.stocks.commands.stocks_connection_manager import StocksConnectionManager
from src.stocks.commands.calculate_stock_margin_requirements_command import CalculateStockMarginRequirementsCommand
from src.stocks.commands.strategies.orb_signal_command import ORBSignalCommand
from src.stocks.commands.end_of_day_exit_command import EndOfDayExitCommand
from src.stocks.commands.time_based_exit_command import TimeBasedExitCommand
from src.stocks.commands.move_stop_order_command import MoveStopOrderCommand

class StocksTradeManager(IObserver):

    def __init__(self, application_context):

        self.subject = application_context.subject
        self.client = application_context.client
        self.state_manager = application_context.state_manager
        self.state_manager.subject.subscribe(self)
        self.application_context = application_context

        self.command_invoker = CommandInvoker()

        # Register stock trading commands
        self.command_invoker.register_command(EVENT_TYPE_PRE_MARKET_SCAN, PreMarketScanCommand(self.application_context))
        self.command_invoker.register_command(EVENT_TYPE_CALCULATE_OPENING_RANGE, CalculateOpeningRangeCommand(self.application_context))
        self.command_invoker.register_command(EVENT_TYPE_ORB_STRATEGY, ORBSignalCommand(self.application_context))
        self.command_invoker.register_command(EVENT_TYPE_OPEN_POSITION, OpenPositionCommand(self.application_context))
        self.command_invoker.register_command(EVENT_TYPE_MANAGE_STOCK_POSITIONS, ManageStockPositionsCommand(self.application_context))
        self.command_invoker.register_command(EVENT_TYPE_CLOSE_ALL_STOCK_POSITIONS, ManageStockPositionsCommand(self.application_context))
        self.command_invoker.register_command(EVENT_TYPE_STOCKS_CONNECTION_CHECK, StocksConnectionManager(self.application_context))
        self.command_invoker.register_command(EVENT_TYPE_CALCULATE_STOCK_MARGINS, CalculateStockMarginRequirementsCommand(self.application_context))

        # Register position management commands
        self.command_invoker.register_command(EVENT_TYPE_END_OF_DAY_EXIT, EndOfDayExitCommand(self.application_context))
        self.command_invoker.register_command(EVENT_TYPE_TIME_BASED_EXIT, TimeBasedExitCommand(self.application_context))
        self.command_invoker.register_command(EVENT_TYPE_MOVE_STOP_ORDER, MoveStopOrderCommand(self.application_context))

    def notify(self, observable, *args):

        event_type = args[0][FIELD_TYPE]
        event = args[0]
        self.command_invoker.execute_command(event_type, event)