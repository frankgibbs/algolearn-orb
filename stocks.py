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

        # Opening range calculation at 7:00 AM PST (10:00 AM ET)
        schedule.every().day.at("07:00").do(self.calculate_opening_range)

        # ORB strategy checks every 30 minutes from 7:00 AM - 12:00 PM PST
        schedule.every().day.at("07:00").do(self.orb_strategy)
        schedule.every().day.at("07:30").do(self.orb_strategy)
        schedule.every().day.at("08:00").do(self.orb_strategy)
        schedule.every().day.at("08:30").do(self.orb_strategy)
        schedule.every().day.at("09:00").do(self.orb_strategy)
        schedule.every().day.at("09:30").do(self.orb_strategy)
        schedule.every().day.at("10:00").do(self.orb_strategy)
        schedule.every().day.at("10:30").do(self.orb_strategy)
        schedule.every().day.at("11:00").do(self.orb_strategy)
        schedule.every().day.at("11:30").do(self.orb_strategy)
        schedule.every().day.at("12:00").do(self.orb_strategy)

        # Position management every minute during market hours
        schedule.every(60).seconds.do(self.manage_positions)

        # Close all positions at 12:50 PM PST (3:50 PM ET)
        schedule.every().day.at("12:50").do(self.close_all_positions)

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
        """Manage open stock positions"""
        market_open = self.state_manager.getConfigValue(CONFIG_MARKET_OPEN)
        if market_open:
            self.subject.notify({FIELD_TYPE: EVENT_TYPE_MANAGE_STOCK_POSITIONS})

    def close_all_positions(self):
        """Close all positions at end of day"""
        self.subject.notify({FIELD_TYPE: EVENT_TYPE_CLOSE_ALL_STOCK_POSITIONS})

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
        CONFIG_ORB_PERIOD_MINUTES: args.orb_period,
        CONFIG_RISK_PERCENTAGE: args.risk_pct,
        CONFIG_MAX_POSITIONS: args.max_positions,
        CONFIG_MIN_PRICE: args.min_price,
        CONFIG_MAX_PRICE: args.max_price,
        CONFIG_MIN_VOLUME: args.min_volume
    }

    client = IBClient(subject, config)
    state_manager = State(client, subject, config)
    application_context = ApplicationContext(state_manager)

    # Initialize all managers
    stocks_service = StocksService(application_context)
    trade_manager = StocksTradeManager(application_context)
    telegram_manager = StocksTelegramManager(application_context)
    database_manager = StocksDatabaseManager(application_context)
    application_context.database_manager = database_manager

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