from src.core.command import Command
from src.core.constants import *
from src.stocks.services.stocks_strategy_service import StocksStrategyService
from src.stocks.services.stocks_scanner_service import StocksScannerService
from src import logger
import pytz
from datetime import datetime

class PreMarketScanCommand(Command):
    """Pre-market scanning for ORB candidates at 5:30 AM PST"""

    def execute(self, event):
        """
        Execute pre-market scan for stock candidates

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.info("Starting pre-market scan for ORB candidates")

        # Get current time for logging and database storage
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        # Initialize services
        strategy_service = StocksStrategyService(self.application_context)
        scanner_service = StocksScannerService(self.application_context)

        # Get and validate configuration parameters - ALL REQUIRED
        min_price = self._get_required_config_value(CONFIG_MIN_PRICE, "minimum price")
        max_price = self._get_required_config_value(CONFIG_MAX_PRICE, "maximum price")
        min_volume = self._get_required_config_value(CONFIG_MIN_VOLUME, "minimum volume")
        min_pre_market_change = self._get_required_config_value(CONFIG_MIN_PRE_MARKET_CHANGE, "minimum pre-market change %")

        # Validate price range
        if min_price >= max_price:
            raise ValueError(f"Invalid price range: min_price (${min_price}) must be < max_price (${max_price})")

        # Validate minimum values
        if min_price <= 0:
            raise ValueError(f"min_price must be > 0, got ${min_price}")
        if min_volume <= 0:
            raise ValueError(f"min_volume must be > 0, got {min_volume:,}")
        if min_pre_market_change < 0:
            raise ValueError(f"min_pre_market_change must be >= 0, got {min_pre_market_change}%")

        logger.info(f"Scanning with filters: Price ${min_price}-${max_price}, Volume {min_volume:,}, Min Change {min_pre_market_change}%")

        # Build scanner criteria
        scan_criteria = {
            "min_price": min_price,
            "max_price": max_price,
            "min_volume": min_volume,
            "min_pre_market_change": min_pre_market_change,
            "max_results": 100  # Get more results to filter down
        }

        # Execute pre-market scanner
        scanner_results = scanner_service.scan_pre_market_movers(scan_criteria)

        # Format results for database storage
        candidates = scanner_service.format_scanner_results(scanner_results, scan_criteria, now)

        # Save results to database
        strategy_service.save_candidates(candidates, now)

        # Send notification
        self.state_manager.sendTelegramMessage(
            f"📊 Pre-market scan at {now.strftime('%I:%M %p PST')}\n"
            f"Found {len(candidates)} ORB candidates"
        )


    def _get_required_config_value(self, config_key, description):
        """
        Get required configuration value - fails loudly if missing

        Args:
            config_key: Configuration key to retrieve (required)
            description: Description for error message (required)

        Returns:
            Configuration value

        Raises:
            ValueError: If config_key or description is None, or if config is missing
        """
        if config_key is None:
            raise ValueError("config_key is REQUIRED")
        if description is None:
            raise ValueError("description is REQUIRED")

        try:
            value = self.state_manager.get_config_value(config_key)
        except KeyError:
            raise ValueError(f"Configuration {config_key} ({description}) is REQUIRED but not configured")

        if value is None:
            raise ValueError(f"Configuration {config_key} ({description}) is REQUIRED but not configured")

        logger.info(f"Using configured {description}: {value}")
        return value