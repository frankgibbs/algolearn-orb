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
        # Clear ATR cache at 5:00 AM PST (before pre-market scan)
        schedule.every().day.at("05:00").do(self.clear_atr_cache)

        # Pre-market scanning at 5:30 AM PST (8:30 AM ET)
        schedule.every().day.at("05:30").do(self.pre_market_scan)

        # Opening range calculation - dynamic based on CONFIG_ORB_TIMEFRAME
        # 5m ORB → 6:35 AM, 15m ORB → 6:45 AM, 30m ORB → 7:00 AM, 60m ORB → 7:30 AM
        orb_timeframe = self.state_manager.get_config_value(CONFIG_ORB_TIMEFRAME)
        if orb_timeframe == 5:
            schedule.every().day.at("06:35").do(self.calculate_opening_range)
        elif orb_timeframe == 15:
            schedule.every().day.at("06:45").do(self.calculate_opening_range)
        elif orb_timeframe == 30:
            schedule.every().day.at("07:00").do(self.calculate_opening_range)
        elif orb_timeframe == 60:
            schedule.every().day.at("07:30").do(self.calculate_opening_range)
        else:
            raise ValueError(f"Invalid CONFIG_ORB_TIMEFRAME: {orb_timeframe}. Must be 5, 15, 30, or 60")

        # ORB strategy checks - dynamic based on CONFIG_ORB_TIMEFRAME
        # Run on clock-aligned intervals from after opening range until 10:00 AM PST
        if orb_timeframe == 5:
            # Check every 5 minutes starting after 6:35 AM until 10:00 AM
            for hour in range(6, 11):  # 6 AM to 10 AM
                for minute in range(0, 60, 5):  # Every 5 minutes: 0, 5, 10, ..., 55
                    if hour == 6 and minute < 40:  # Skip times before 6:40 AM
                        continue
                    if hour == 10 and minute > 0:  # Only include 10:00, not 10:05+
                        break
                    schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(self.orb_strategy)
        elif orb_timeframe == 15:
            # Check every 15 minutes starting after 6:45 AM until 10:00 AM
            for hour in range(7, 11):  # 7 AM to 10 AM
                for minute in [0, 15, 30, 45]:
                    if hour == 10 and minute > 0:  # Only include 10:00, not 10:15/10:30/10:45
                        break
                    schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(self.orb_strategy)
        elif orb_timeframe == 30:
            # Check every 30 minutes starting after 7:00 AM until 10:00 AM
            for hour in range(7, 11):  # 7 AM to 10 AM
                for minute in [0, 30]:
                    if hour == 10 and minute > 0:  # Only include 10:00, not 10:30
                        break
                    schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(self.orb_strategy)
        elif orb_timeframe == 60:
            # Check every hour starting after 7:30 AM until 10:00 AM
            for hour in range(8, 11):  # 8 AM to 10 AM
                schedule.every().day.at(f"{hour:02d}:00").do(self.orb_strategy)

        # Position state transitions every 30 seconds
        schedule.every(30).seconds.do(self.manage_positions)

        # Option position state transitions every 30 seconds
        schedule.every(30).seconds.do(self.manage_option_positions)

        # PowerOptions position state transitions every 30 seconds
        schedule.every(30).seconds.do(self.manage_power_options_positions)

        # Trailing stop management every minute during market hours
        schedule.every(60).seconds.do(self.move_stop_orders)

        # Time-based exit checks every minute during market hours
        # schedule.every(60).seconds.do(self.time_based_exits)  # Disabled: Not part of Academic ORB Strategy

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

    def __run_dashboard_api(self):
        """Run the Dashboard API server"""
        from src.api.stocks_dashboard_api import StocksDashboardApi
        dashboard_api = StocksDashboardApi(self.application_context)
        dashboard_api.run(host="0.0.0.0", port=8080)

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

    def manage_option_positions(self):
        """Monitor option position state transitions (PENDING → OPEN)"""
        market_open = self.state_manager.getConfigValue(CONFIG_MARKET_OPEN)
        if market_open:
            self.subject.notify({FIELD_TYPE: EVENT_TYPE_MANAGE_OPTION_POSITIONS})

    def manage_power_options_positions(self):
        """Monitor PowerOptions equity and option position state transitions"""
        market_open = self.state_manager.getConfigValue(CONFIG_MARKET_OPEN)
        if market_open:
            self.subject.notify({FIELD_TYPE: EVENT_TYPE_MANAGE_POWER_OPTIONS_POSITIONS})

    def move_stop_orders(self):
        """Handle trailing stop order modifications"""
        market_open = self.state_manager.getConfigValue(CONFIG_MARKET_OPEN)
        if market_open:
            self.subject.notify({FIELD_TYPE: EVENT_TYPE_MOVE_STOP_ORDER})

    # def time_based_exits(self):
    #     """Check for time-based exits on stagnant positions"""
    #     # Disabled: Not part of Academic ORB Strategy
    #     market_open = self.state_manager.getConfigValue(CONFIG_MARKET_OPEN)
    #     if market_open:
    #         self.subject.notify({FIELD_TYPE: EVENT_TYPE_TIME_BASED_EXIT})

    def end_of_day_exit(self):
        """Close all positions at end of day and generate daily report"""
        self.subject.notify({FIELD_TYPE: EVENT_TYPE_END_OF_DAY_EXIT})

    def smart_connection_check(self):
        """Check IB connection status"""
        self.subject.notify({FIELD_TYPE: EVENT_TYPE_STOCKS_CONNECTION_CHECK})

    def clear_atr_cache(self):
        """Clear ATR cache daily to prevent memory accumulation"""
        from src.stocks.services.atr_service import ATRService
        ATRService.clear_cache()
        logger.info("ATR cache cleared (daily maintenance)")

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

            # Start Dashboard API thread
            logger.debug("Starting Dashboard API")
            dashboard_api_thread = threading.Thread(target=self.__run_dashboard_api, daemon=True)
            dashboard_api_thread.start()


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
    parser.add_argument("--min-pre-market-change", required=True, type=float, help="Minimum pre-market change percentage")
    # Legacy parameters removed (not part of Academic ORB Strategy):
    # - stagnation-minutes (no time-based exits)
    # - initial-stop-loss-ratio (uses ATR instead)
    # - trailing-stop-ratio (uses ATR instead)
    # - take-profit-ratio (no take-profit targets)
    parser.add_argument("--min-range-pct", required=True, type=float, help="Minimum opening range percentage")
    parser.add_argument("--max-range-pct", required=True, type=float, help="Maximum opening range percentage")

    # Relative Volume parameters (per academic paper)
    parser.add_argument("--volume-lookback-days", required=True, type=int, help="Lookback days for Relative Volume calculation (14 per paper)")
    parser.add_argument("--top-n-stocks", required=True, type=int, help="Top N stocks by relative volume (20 per paper)")
    parser.add_argument("--min-relative-volume", required=True, type=float, help="Minimum relative volume threshold (100% per paper)")
    parser.add_argument("--relative-volume-lookback", required=True, type=int, help="Lookback days for relative volume average (14 per paper)")

    # ATR parameters (per academic paper)
    parser.add_argument("--atr-period", required=True, type=int, help="ATR period in days (14 per paper)")
    parser.add_argument("--atr-stop-multiplier", required=True, type=float, help="ATR stop multiplier (0.10 = 10% per paper)")
    parser.add_argument("--min-atr", required=True, type=float, help="Minimum ATR value for scan filtering")

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
        CONFIG_MIN_PRE_MARKET_CHANGE: args.min_pre_market_change,
        # Legacy parameters removed (not part of Academic ORB Strategy):
        # CONFIG_STAGNATION_THRESHOLD_MINUTES, CONFIG_INITIAL_STOP_LOSS_RATIO,
        # CONFIG_TRAILING_STOP_RATIO, CONFIG_TAKE_PROFIT_RATIO
        CONFIG_MIN_RANGE_PCT: args.min_range_pct,
        CONFIG_MAX_RANGE_PCT: args.max_range_pct,
        # Relative Volume parameters (per academic paper)
        CONFIG_ORB_VOLUME_LOOKBACK_DAYS: args.volume_lookback_days,
        CONFIG_TOP_N_STOCKS: args.top_n_stocks,
        CONFIG_MIN_RELATIVE_VOLUME: args.min_relative_volume,
        CONFIG_RELATIVE_VOLUME_LOOKBACK: args.relative_volume_lookback,
        # ATR parameters (per academic paper)
        CONFIG_ATR_PERIOD: args.atr_period,
        CONFIG_ATR_STOP_MULTIPLIER: args.atr_stop_multiplier,
        CONFIG_MIN_ATR: args.min_atr
    }

    client = IBClient(subject, config)
    state_manager = State(client, subject, config)
    application_context = ApplicationContext(state_manager)

    # Initialize database_manager FIRST so commands can access it
    database_manager = StocksDatabaseManager(application_context)
    application_context.database_manager = database_manager

    # Initialize options database manager and services
    from src.options.option_database_manager import OptionDatabaseManager
    from src.options.services.option_order_service import OptionOrderService
    from src.options.services.option_position_service import OptionPositionService
    from src.options.services.option_analyzer_service import OptionAnalyzerService

    option_db_manager = OptionDatabaseManager(application_context)
    application_context.option_db_manager = option_db_manager

    option_order_service = OptionOrderService(application_context)
    application_context.option_order_service = option_order_service

    option_position_service = OptionPositionService(application_context)
    application_context.option_position_service = option_position_service

    option_analyzer_service = OptionAnalyzerService(application_context)
    application_context.option_analyzer_service = option_analyzer_service

    # Initialize equity database manager for PowerOptions strategy
    # NOTE: EquityService is instantiated on-demand to avoid storing state
    from src.equity.equity_holding_manager import EquityHoldingManager

    equity_db_manager = EquityHoldingManager(application_context)
    application_context.equity_db_manager = equity_db_manager

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