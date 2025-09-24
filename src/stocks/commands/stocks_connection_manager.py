from src.core.command import Command
from src.core.constants import *
from src import logger
import pytz
from datetime import datetime

class StocksConnectionManager(Command):
    """Manages IB connection and validates market hours for stock trading"""

    def execute(self, event):
        """
        Execute connection management and market hours validation
        Maintains connection 24/7 for monitoring and preparation

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.info("Managing stocks connection and tracking market hours")

        # Get current time in Pacific timezone
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        # Always manage connection regardless of market hours
        if not self._is_connected():
            self._establish_connection()
        else:
            self._maintain_connection()

        # Track market hours for informational purposes
        market_status = self._get_market_status(now)

        # Update state
        is_connected = self.client.isConnected() if self.client else False
        self.state_manager.set_state("connected", is_connected)
        self.state_manager.set_state("market_status", market_status)

        # Trigger margin calculation after successful connection
        if is_connected:
            self.application_context.subject.notify({
                FIELD_TYPE: EVENT_TYPE_CALCULATE_STOCK_MARGINS
            })
            logger.info("Triggered stock margin calculation")

        # Log status
        logger.info(f"Connection: {'Connected' if is_connected else 'Disconnected'}")
        logger.info(f"Market Status: {market_status}")
        logger.info(f"Current PST time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    def _get_market_status(self, now):
        """
        Determine current market status based on PST time

        Args:
            now: Current datetime in Pacific timezone (required)

        Returns:
            String indicating market status

        Raises:
            ValueError: If now is None
        """
        if now is None:
            raise ValueError("now is REQUIRED")

        # Check if it's a weekday (Monday=0, Friday=4)
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return "CLOSED_WEEKEND"

        # Market hours in PST:
        # Pre-market: 5:30 AM - 6:30 AM
        # Regular: 6:30 AM - 1:00 PM
        # After-hours: 1:00 PM - 5:00 PM

        hour = now.hour
        minute = now.minute

        # Check conditions in proper order to avoid overlaps
        if hour < 5 or (hour == 5 and minute < 30):
            return "CLOSED"
        elif hour == 5 and minute >= 30:
            return "PRE_MARKET"
        elif hour == 6 and minute < 30:
            return "PRE_MARKET"
        elif hour == 6 and minute >= 30:
            return "OPEN"
        elif 7 <= hour < 13:
            return "OPEN"
        elif 13 <= hour < 17:
            return "AFTER_HOURS"
        else:
            return "CLOSED"

    def _is_connected(self):
        """Check if we have an active connection."""
        return self.client.isConnected() if self.client else False

    def _establish_connection(self):
        """Establish initial connection to IB Gateway."""
        try:
            logger.info("Establishing connection to IB Gateway")

            if self.client:
                # Use the existing connection logic from IBClient
                self.client.do_connect()

                # Wait a moment for connection to establish
                import time
                time.sleep(2)

                # Verify connection is working
                if self._test_connection():
                    logger.info("Connection established successfully")
                    self.state_manager.sendTelegramMessage("✅ Stocks service connected to IB Gateway")
                else:
                    logger.warning("Connection attempt failed")
            else:
                logger.error("No client available for connection")

        except Exception as e:
            logger.error(f"Failed to establish connection: {e}")
            self.state_manager.sendTelegramMessage(f"❌ Stocks service failed to connect: {type(e).__name__}")

    def _maintain_connection(self):
        """Maintain existing connection with health checks."""
        try:
            logger.debug("Performing connection health check")

            # Use the existing connection check method
            if self.client:
                self.client.check_connection()

        except Exception as e:
            logger.error(f"Connection health check error: {e}")
            self._handle_connection_loss()

    def _test_connection(self):
        """Test if the connection is actually working."""
        try:
            if self.client:
                self.client.check_connection()
                return True
            return False
        except Exception as e:
            logger.error(f"Connection test error: {e}")
            return False

    def _handle_connection_loss(self):
        """Handle connection loss by attempting reconnection."""
        logger.warning("Connection lost - attempting reconnection")

        self.state_manager.sendTelegramMessage("⚠️ Stocks service connection lost - attempting reconnection")

        # Attempt to reconnect
        self._establish_connection()

    def _attempt_reconnection(self):
        """Legacy method - redirects to _establish_connection"""
        self._establish_connection()

    def _validate_trading_permissions(self):
        """
        Validate that the account has stock trading permissions

        Returns:
            Boolean indicating if stock trading is allowed
        """
        # TODO: Implement actual permission validation via IB API
        # For now, assume permissions are valid

        logger.info("Validating stock trading permissions")
        return True