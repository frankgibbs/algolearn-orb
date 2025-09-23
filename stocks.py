#!/usr/bin/env python3
"""
Stock Trading Service with ORB Strategy
Times in PST/PDT (Pacific Time)
NO DEFAULTS - All parameters must be explicit
"""

from src.core.ibclient import IBClient
from src.core.observer import Subject, IObserver
from src.core.state import State
from src.stocks.stocks_database_manager import StocksDatabaseManager
from src.stocks.stocks_trade_manager import StocksTradeManager
from src.stocks.stocks_telegram_manager import StocksTelegramManager
from src.core.application_context import ApplicationContext
from src.core.constants import *
from src.api.stocks_mcp_api import StocksMcpApi
from src import logger
import warnings
import time
import threading
import argparse
import sys
import schedule
import pytz
from datetime import datetime

warnings.simplefilter(action='ignore', category=FutureWarning)

class StocksService(IObserver):
    """Stock trading service with ORB strategy"""

    def __init__(self, application_context: ApplicationContext):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.subject = application_context.subject
        self.client = application_context.client
        self.state_manager = application_context.state_manager
        self.state_manager.subject.subscribe(self)
        self.application_context = application_context


        # Schedule trading tasks - All times in PST
        # Pre-market scanning at 5:30 AM PST (8:30 AM ET)
        schedule.every().day.at("05:30").do(self.pre_market_scan)

        # Opening range calculation - dynamic based on CONFIG_ORB_TIMEFRAME
        # 15m ORB → 6:45 AM, 30m ORB → 7:00 AM, 60m ORB → 7:30 AM
        orb_timeframe = self.state_manager.get_config_value(CONFIG_ORB_TIMEFRAME)
        if orb_timeframe == 15:
            schedule.every().day.at("06:45").do(self.calculate_opening_range)
        elif orb_timeframe == 30:
            schedule.every().day.at("07:00").do(self.calculate_opening_range)
        elif orb_timeframe == 60:
            schedule.every().day.at("07:30").do(self.calculate_opening_range)
        else:
            raise ValueError(f"Invalid CONFIG_ORB_TIMEFRAME: {orb_timeframe}. Must be 15, 30, or 60")

        # ORB strategy checks - dynamic based on CONFIG_ORB_TIMEFRAME
        # Run on clock-aligned intervals from after opening range until 12:50 PM PST
        if orb_timeframe == 15:
            # Check every 15 minutes starting after 6:45 AM
            for hour in range(7, 13):  # 7 AM to 12 PM
                for minute in [0, 15, 30, 45]:
                    if hour == 12 and minute > 45:  # Stop before EOD exit at 12:50
                        break
                    schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(self.orb_strategy)
        elif orb_timeframe == 30:
            # Check every 30 minutes starting after 7:00 AM
            for hour in range(7, 13):  # 7 AM to 12 PM
                for minute in [0, 30]:
                    if hour == 12 and minute > 30:  # Stop before EOD exit at 12:50
                        break
                    schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(self.orb_strategy)
        elif orb_timeframe == 60:
            # Check every hour starting after 7:30 AM
            for hour in range(8, 13):  # 8 AM to 12 PM
                schedule.every().day.at(f"{hour:02d}:00").do(self.orb_strategy)

        # Position state transitions every 30 seconds
        schedule.every(30).seconds.do(self.manage_positions)

        # Trailing stop management every minute during market hours
        schedule.every(60).seconds.do(self.move_stop_orders)

        # Time-based exit checks every minute during market hours
        schedule.every(60).seconds.do(self.time_based_exits)

        # End-of-day position closure at 12:50 PM PST (3:50 PM ET)
        schedule.every().day.at("12:50").do(self.end_of_day_exit)

        # Connection checks every 5 minutes (following forex pattern)
        for minute in range(0, 60, 5):
            schedule.every().hour.at(f":{minute:02d}").do(self.smart_connection_check)

        logger.info("Stocks service initialized - ORB strategy ready")

    def __start_scheduler(self):
        """Run the scheduler loop"""
        while True:
            time.sleep(1)
            try:
                schedule.run_pending()
            except Exception as e:
                logger.error(e, exc_info=True)

    def __run_mcp_api(self):
        """Run the MCP API server"""
        mcp_api = StocksMcpApi(self.application_context)
        mcp_api.run(host="0.0.0.0", port=8003)

    def pre_market_scan(self):
        """Trigger pre-market scan command"""
        stopped = self.state_manager.getConfigValue(CONFIG_STOPPED)
        if stopped:
            return
        self.subject.notify({FIELD_TYPE: EVENT_TYPE_PRE_MARKET_SCAN})

    def calculate_opening_range(self):
        """Trigger opening range calculation"""
        stopped = self.state_manager.getConfigValue(CONFIG_STOPPED)
        if stopped:
            return
        self.subject.notify({FIELD_TYPE: EVENT_TYPE_CALCULATE_OPENING_RANGE})

    def orb_strategy(self):
        """Trigger ORB strategy check"""
        stopped = self.state_manager.getConfigValue(CONFIG_STOPPED)
        if stopped:
            return
        self.subject.notify({FIELD_TYPE: EVENT_TYPE_ORB_STRATEGY})

    def manage_positions(self):
        """Monitor position state transitions (PENDING → OPEN → CLOSED)"""
        market_open = self.state_manager.getConfigValue(CONFIG_MARKET_OPEN)
        if market_open:
            self.subject.notify({FIELD_TYPE: EVENT_TYPE_MANAGE_STOCK_POSITIONS})

    def move_stop_orders(self):
        """Handle trailing stop order modifications"""
        market_open = self.state_manager.getConfigValue(CONFIG_MARKET_OPEN)
        if market_open:
            self.subject.notify({FIELD_TYPE: EVENT_TYPE_MOVE_STOP_ORDER})

    def time_based_exits(self):
        """Check for time-based exits on stagnant positions"""
        market_open = self.state_manager.getConfigValue(CONFIG_MARKET_OPEN)
        if market_open:
            self.subject.notify({FIELD_TYPE: EVENT_TYPE_TIME_BASED_EXIT})

    def end_of_day_exit(self):
        """Close all positions at end of day and generate daily report"""
        self.subject.notify({FIELD_TYPE: EVENT_TYPE_END_OF_DAY_EXIT})

    def smart_connection_check(self):
        """Check IB connection status"""
        self.subject.notify({FIELD_TYPE: EVENT_TYPE_STOCKS_CONNECTION_CHECK})

    def notify(self, observable, *args):
        """Handle start event"""
        event_type = args[0][FIELD_TYPE]

        if event_type == EVENT_TYPE_START:
            # Start scheduler thread
            logger.debug("Starting scheduler")
            sched = threading.Thread(target=self.__start_scheduler)
            sched.start()

            # Start MCP API thread
            logger.debug("Starting MCP API")
            mcp_api_thread = threading.Thread(target=self.__run_mcp_api, daemon=True)
            mcp_api_thread.start()


def main():
    parser = argparse.ArgumentParser(description="Stock Trading Service with ORB Strategy")

    # REQUIRED parameters - no defaults
    parser.add_argument("-p", "--port", required=True, type=int, help="IB gateway port")
    parser.add_argument("-i", "--host", required=True, help="IB host")
    parser.add_argument("-c", "--client", required=True, type=int, help="IB client Id")
    parser.add_argument("-u", "--account", required=True, help="IB Account")
    parser.add_argument("--token", required=True, help="Telegram bot token")
    parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    parser.add_argument("--orb-period", required=True, type=int, help="ORB period in minutes")
    parser.add_argument("--risk-pct", required=True, type=float, help="Risk percentage per trade")
    parser.add_argument("--max-positions", required=True, type=int, help="Maximum concurrent positions")
    parser.add_argument("--min-price", required=True, type=float, help="Minimum stock price")
    parser.add_argument("--max-price", required=True, type=float, help="Maximum stock price")
    parser.add_argument("--min-volume", required=True, type=int, help="Minimum daily volume")
    parser.add_argument("--stagnation-minutes", required=True, type=int, help="Minutes before position is considered stagnant")
    parser.add_argument("--trailing-stop-ratio", type=float, default=0.5, help="Trailing stop ratio (default: 0.5)")
    parser.add_argument("--take-profit-ratio", type=float, default=1.5, help="Take profit ratio (default: 1.5)")
    parser.add_argument("--min-range-pct", type=float, default=0.5, help="Minimum opening range %% (default: 0.5)")
    parser.add_argument("--max-range-pct", type=float, default=3.0, help="Maximum opening range %% (default: 3.0)")

    args = parser.parse_args()

    subject = Subject()

    # Configuration with EXPLICIT values - NO DEFAULTS
    config = {
        CONFIG_HOST: args.host,
        CONFIG_PORT: args.port,
        CONFIG_CLIENT_ID: args.client,
        CONFIG_ACCOUNT: args.account,
        CONFIG_TELEGRAM_TOKEN: args.token,
        CONFIG_TELEGRAM_CHAT_ID: args.chat_id,
        CONFIG_STOPPED: False,
        CONFIG_CONNECTED: False,
        CONFIG_MARKET_OPEN: True,  # Allow stock trading during market hours
        CONFIG_DEBUG: False,
        CONFIG_TIMEZONE: 'US/Pacific',
        # ORB Strategy specific parameters
        CONFIG_ORB_TIMEFRAME: args.orb_period,
        CONFIG_RISK_PERCENTAGE: args.risk_pct,
        CONFIG_MAX_POSITIONS: args.max_positions,
        CONFIG_MIN_PRICE: args.min_price,
        CONFIG_MAX_PRICE: args.max_price,
        CONFIG_MIN_VOLUME: args.min_volume,
        CONFIG_STAGNATION_THRESHOLD_MINUTES: args.stagnation_minutes,
        CONFIG_TRAILING_STOP_RATIO: args.trailing_stop_ratio,
        CONFIG_TAKE_PROFIT_RATIO: args.take_profit_ratio,
        CONFIG_MIN_RANGE_PCT: args.min_range_pct,
        CONFIG_MAX_RANGE_PCT: args.max_range_pct
    }

    client = IBClient(subject, config)
    state_manager = State(client, subject, config)
    application_context = ApplicationContext(state_manager)

    # Initialize database_manager FIRST so commands can access it
    database_manager = StocksDatabaseManager(application_context)
    application_context.database_manager = database_manager

    # Initialize all other managers
    stocks_service = StocksService(application_context)
    trade_manager = StocksTradeManager(application_context)
    telegram_manager = StocksTelegramManager(application_context)

    # Start Telegram bot in background thread
    telegram_thread = threading.Thread(
        target=telegram_manager.start,
        daemon=True,
        name="TelegramBot"
    )
    telegram_thread.start()
    logger.info("Telegram bot started in background thread")

    # Start the system
    subject.notify({FIELD_TYPE: EVENT_TYPE_START})
    subject.notify({FIELD_TYPE: EVENT_TYPE_STOCKS_CONNECTION_CHECK})

    # Keep the service running
    logger.info("Stocks service running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
            # Process any queued events
            subject.processQueue()
    except KeyboardInterrupt:
        logger.info("Stocks service stopped by user")
    except Exception as e:
        logger.error(f"Stocks service error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()