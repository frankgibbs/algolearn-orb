from src.core.observer import IObserver
from src.core.constants import *
from src import logger

class StocksTelegramManager(IObserver):
    """Handles Telegram notifications for stock trading"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.subject = application_context.subject
        self.client = application_context.client
        self.state_manager = application_context.state_manager
        self.application_context = application_context

        # Subscribe to events
        self.state_manager.subject.subscribe(self)

        logger.info("StocksTelegramManager initialized")

    def notify(self, observable, *args):
        """Handle events from observer pattern"""
        try:
            if not args or len(args) == 0:
                return

            event = args[0]
            event_type = event.get(FIELD_TYPE)

            if event_type == EVENT_TYPE_TELEGRAM_MESSAGE:
                self._send_message(event.get(FIELD_MESSAGE, ""))

        except Exception as e:
            logger.error(f"Error in StocksTelegramManager.notify: {e}")

    def _send_message(self, message):
        """Send message via Telegram"""
        if not message:
            logger.warning("Empty message provided to Telegram")
            return

        try:
            # TODO: Implement actual Telegram sending logic
            # For now, just log the message
            logger.info(f"Telegram (Stocks): {message}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def send_scan_results(self, candidates, scan_time):
        """Send pre-market scan results"""
        if not candidates:
            message = f"📊 Pre-market scan at {scan_time.strftime('%I:%M %p PST')}: No candidates found"
        else:
            symbols = [c.symbol for c in candidates[:10]]  # Top 10
            message = f"📊 Pre-market scan at {scan_time.strftime('%I:%M %p PST')}\n"
            message += f"Found {len(candidates)} candidates:\n"
            message += f"Top 10: {', '.join(symbols)}"

        self.state_manager.sendTelegramMessage(message)

    def send_opening_range_calculated(self, symbol, range_high, range_low, range_size_pct):
        """Send opening range calculation notification"""
        message = f"📏 Opening range calculated for {symbol}\n"
        message += f"Range: ${range_low:.2f} - ${range_high:.2f}\n"
        message += f"Size: {range_size_pct:.1f}%"

        self.state_manager.sendTelegramMessage(message)

    def send_trade_signal(self, symbol, action, confidence, reasoning):
        """Send trade signal notification"""
        if action not in ["LONG", "SHORT"]:
            logger.warning(f"Invalid action for trade signal: {action}")
            return

        direction_emoji = "🟢" if action == "LONG" else "🔴"
        message = f"{direction_emoji} ORB Signal: {action} {symbol}\n"
        message += f"Confidence: {confidence}%\n"
        message += f"Reason: {reasoning}"

        self.state_manager.sendTelegramMessage(message)

    def send_position_update(self, symbol, action, entry_price, current_pnl):
        """Send position update notification"""
        pnl_emoji = "📈" if current_pnl >= 0 else "📉"
        message = f"{pnl_emoji} Position Update: {action} {symbol}\n"
        message += f"Entry: ${entry_price:.2f}\n"
        message += f"P&L: ${current_pnl:.2f}"

        self.state_manager.sendTelegramMessage(message)