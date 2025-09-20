from src.core.command import Command
from src.core.constants import *
from src import logger
import pytz
from datetime import datetime

class StocksConnectionManager(Command):
    """Manages IB connection and validates market hours for stock trading"""

    def execute(self, event):
        """
        Execute connection check and market hours validation

        Args:
            event: Event data (required)

        Raises:
            ValueError: If event is None
        """
        if event is None:
            raise ValueError("event is REQUIRED")

        logger.info("Checking stocks connection and market hours")

        # Check IB connection status
        is_connected = self.client.isConnected() if self.client else False

        # Get current time in Pacific timezone
        pacific_tz = pytz.timezone('US/Pacific')
        now = datetime.now(pacific_tz)

        # Validate market hours and weekday
        market_status = self._get_market_status(now)

        # Update state
        self.state_manager.set_state("connected", is_connected)
        self.state_manager.set_state("market_status", market_status)

        # Log status
        logger.info(f"Connection: {'Connected' if is_connected else 'Disconnected'}")
        logger.info(f"Market Status: {market_status}")
        logger.info(f"Current PST time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # Attempt reconnection if needed
        if not is_connected:
            self._attempt_reconnection()

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

        if hour < 5 or (hour == 5 and minute < 30):
            return "CLOSED"
        elif hour == 5 and minute >= 30:
            return "PRE_MARKET"
        elif 6 <= hour < 13:
            return "OPEN"
        elif hour == 6 and minute < 30:
            return "PRE_MARKET"
        elif 13 <= hour < 17:
            return "AFTER_HOURS"
        else:
            return "CLOSED"

    def _attempt_reconnection(self):
        """Attempt to reconnect to IB Gateway"""
        try:
            if self.client:
                logger.info("Attempting to reconnect to IB Gateway...")

                # Get connection parameters from config
                host = self.state_manager.get_config_value(CONFIG_HOST)
                port = self.state_manager.get_config_value(CONFIG_PORT)
                client_id = self.state_manager.get_config_value(CONFIG_CLIENT_ID)

                if not host or not port or not client_id:
                    raise ValueError("Missing connection parameters in config")

                # Attempt connection
                self.client.connect(host, port, client_id)
                logger.info("Reconnection attempt initiated")

                # Send notification
                self.state_manager.sendTelegramMessage(
                    f"🔌 Stocks service reconnection attempt to {host}:{port}"
                )
            else:
                logger.error("No client available for reconnection")

        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            self.state_manager.sendTelegramMessage(f"🚨 Stocks reconnection failed: {e}")

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