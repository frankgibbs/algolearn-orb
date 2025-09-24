from src.core.command import Command
from src.core.constants import FIELD_STOCK_MARGIN_REQUIREMENTS
from src.stocks.stocks_config import STOCK_SYMBOLS
from src import logger
from datetime import datetime


class CalculateStockMarginRequirementsCommand(Command):
    """
    Command to calculate and cache margin requirements for stock trading.

    This command fetches margin requirements from IB for all configured stocks
    to provide standardized margin per share for position sizing calculations.
    """

    def __init__(self, application_context):
        super().__init__(application_context)

        # Initialize as None - will be calculated when execute() is called
        self.required_margins = None

        # Load existing cache from state
        self.cache = self.state_manager.get_state(FIELD_STOCK_MARGIN_REQUIREMENTS) or {}

    def calculate_required_margins(self) -> dict:
        """
        Calculate margin requirements for all configured stock symbols

        Returns:
            Dictionary of required margins with None values (to be populated)
        """
        required_margins = {}

        for symbol in STOCK_SYMBOLS:
            # Add all configured stocks for margin calculation
            required_margins[symbol] = None

        logger.info(f"Calculated required margins for {len(required_margins)} stocks: {list(required_margins.keys())}")
        return required_margins

    def execute(self, event):
        """Execute the margin requirements calculation command"""
        logger.info("Starting stock margin requirements calculation for position sizing")

        # Calculate required margins dynamically from configured stocks
        if self.required_margins is None:
            self.required_margins = self.calculate_required_margins()

        # Fetch fresh margin requirements from IB
        logger.info("Fetching fresh stock margin requirements from IB")
        self.fetch_current_margins()

        # Apply synthetic margins for stocks with zero/low margins
        self.apply_synthetic_margins()

        # Save updated cache to state
        self.state_manager.set_state(FIELD_STOCK_MARGIN_REQUIREMENTS, self.cache)

        logger.info("Stock margin requirements calculation completed successfully")
        return self.cache

    def fetch_current_margins(self, min_margin_threshold=10.0):
        """Fetch current margin requirements from IB for all configured stocks"""
        logger.info("Fetching current stock margin requirements from IB...")

        # Clear previous cache
        self.cache = {}

        # Process each stock for margin calculation
        for symbol in self.required_margins.keys():
            self._process_stock_margin(symbol, min_margin_threshold)

        # Validate that we have some real margins for average calculation
        if not self.cache:
            logger.error("Failed to calculate margin requirements for any stocks")
            raise RuntimeError("No stock margin requirements could be calculated - check market status and IB connection")

        logger.info(f"Successfully cached margin requirements for {len(self.cache)} stocks")

    def _process_stock_margin(self, symbol, min_margin_threshold):
        """Process margin calculation for a single stock"""
        try:
            # Get margin per share using what-if order - let exceptions propagate
            margin_per_share = self.client.get_margin_per_share(symbol)

            # Check if margin is too low (likely due to open position or market closed)
            if margin_per_share <= min_margin_threshold:
                logger.info(f"{symbol} has zero/low margin (${margin_per_share:.2f}) - likely open position or market closed, will use average margin")
                # Don't store in cache, let apply_synthetic_margins handle it
                return

            # Store margin per share with metadata
            self.cache[symbol] = {
                'margin': margin_per_share,
                'synthetic': False,
                'timestamp': datetime.now().isoformat()
            }

            logger.info(f"Cached margin for {symbol}: ${margin_per_share:.2f} per share")

        except Exception as e:
            logger.warning(f"Could not get margin for {symbol}: {e}")
            # Don't store in cache, let apply_synthetic_margins handle it

    def apply_synthetic_margins(self):
        """Calculate average margin from real margins and apply to stocks without margins"""
        # Calculate average margin per share from real (non-synthetic) margins only
        valid_margins = []
        for symbol, margin_data in self.cache.items():
            if not margin_data['synthetic']:
                valid_margins.append(margin_data['margin'])

        if not valid_margins:
            logger.warning("No valid margins found to calculate average - using fallback margin")
            # Use a reasonable fallback for stocks (typically around $25-50 per share for most stocks)
            average_margin = 30.0
        else:
            average_margin = sum(valid_margins) / len(valid_margins)
            logger.info(f"Calculated average margin per share from {len(valid_margins)} real margins: ${average_margin:.2f}")

        # Apply synthetic margins to stocks that weren't processed earlier
        synthetic_count = 0
        for symbol in self.required_margins.keys():
            if symbol not in self.cache:
                reason = "zero margin (likely open position or market closed)"

                self.cache[symbol] = {
                    'margin': average_margin,
                    'synthetic': True,
                    'reason': reason,
                    'timestamp': datetime.now().isoformat()
                }
                synthetic_count += 1
                logger.info(f"Applied synthetic margin for {symbol}: ${average_margin:.2f} per share (reason: {reason})")

        logger.info(f"Applied synthetic margins to {synthetic_count} stocks - total cached stocks: {len(self.cache)}")