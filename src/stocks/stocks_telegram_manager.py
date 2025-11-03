from src.core.observer import IObserver
from src.core.constants import *
from src import logger
from src.stocks.stocks_database_manager import StocksDatabaseManager

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import ParseMode
from prettytable import PrettyTable
import requests
import urllib
from io import BytesIO
from datetime import datetime
import pytz
import threading

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

    def start(self):
        """Start Telegram bot with command handlers - v13.5 pattern"""
        token = self.state_manager.getConfigValue(CONFIG_TELEGRAM_TOKEN)
        if token is None:
            logger.warning("CONFIG_TELEGRAM_TOKEN not configured, Telegram bot disabled")
            return

        try:
            # v13.5 uses Updater with use_context=True
            updater = Updater(token, use_context=True)

            # Get the dispatcher to register handlers
            dp = updater.dispatcher

            # Register command handlers - v13.5 style
            dp.add_handler(CommandHandler("plot", self.send_plot))
            dp.add_handler(CommandHandler("ranges", self.send_ranges))
            dp.add_handler(CommandHandler("calc", self.calc_ranges))
            dp.add_handler(CommandHandler("break", self.check_breakout))
            dp.add_handler(CommandHandler("cancel", self.cancel_order))
            dp.add_handler(CommandHandler("reset", self.reset_positions))
            dp.add_handler(CommandHandler("pnl", self.send_pnl))
            dp.add_handler(CommandHandler("orders", self.send_orders))
            dp.add_handler(CommandHandler("margin", self.send_margins))
            dp.add_handler(CommandHandler("scan", self.manual_scan))
            dp.add_handler(CommandHandler("list", self.list_candidates))
            dp.add_handler(CommandHandler("va", self.volume_analysis))

            # Add error handler
            dp.add_error_handler(self.error)

            logger.info("Starting Telegram bot...")
            # Start the Bot
            updater.start_polling()
            logger.info("Telegram bot started successfully")

        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")

    def send_plot(self, update, context):
        """Handle /plot [symbol] command"""
        try:
            symbol = None
            if context.args:
                symbol = context.args[0].upper()
            else:
                update.message.reply_text("Usage: /plot SYMBOL")
                return

            # Get data from service
            from src.stocks.services.stocks_strategy_service import StocksStrategyService
            from src.stocks.services.stocks_chart_service import StocksChartService

            strategy_service = StocksStrategyService(self.application_context)
            plot_data, opening_range = strategy_service.get_plot_data(symbol)

            if plot_data is None or plot_data.empty:
                update.message.reply_text(f"No data available for {symbol}")
                return

            # Generate chart
            chart_service = StocksChartService()
            buf = chart_service.generate_candlestick_chart(plot_data, symbol, opening_range)

            # Send photo using v13.5 method
            context.bot.sendPhoto(
                chat_id=update.effective_chat.id,
                photo=buf,
                caption=f"📊 {symbol} - {datetime.now().strftime('%Y-%m-%d')}"
            )

        except Exception as e:
            logger.error(f"Error in send_plot: {e}", exc_info=True)
            update.message.reply_text(f"Error: {str(e)}")

    def send_ranges(self, update, context):
        """Handle /ranges command"""
        try:
            # Get data from service
            from src.stocks.services.stocks_strategy_service import StocksStrategyService
            strategy_service = StocksStrategyService(self.application_context)
            ranges = strategy_service.get_opening_ranges_summary()

            if not ranges:
                update.message.reply_text("No opening ranges calculated today")
                return

            # Use shared formatting method
            message = strategy_service.format_ranges_table(ranges)
            update.message.reply_text(message, parse_mode=ParseMode.HTML)

        except Exception as e:
            logger.error(f"Error in send_ranges: {e}", exc_info=True)
            update.message.reply_text(f"Error: {str(e)}")

    def calc_ranges(self, update, context):
        """Handle /calc command - Calculate opening ranges on demand"""
        try:
            timeframe = self.state_manager.getConfigValue(CONFIG_ORB_TIMEFRAME)
            update.message.reply_text(f"📊 Calculating {timeframe}m opening ranges...")

            # Trigger the calculation (synchronous - will complete before returning)
            event = {FIELD_TYPE: EVENT_TYPE_CALCULATE_OPENING_RANGE}
            self.subject.notify(event)

        except Exception as e:
            logger.error(f"Error in calc_ranges: {e}", exc_info=True)
            update.message.reply_text(f"Error: {str(e)}")

    def check_breakout(self, update, context):
        """Handle /break command - Check for ORB breakout signals on demand"""
        try:
            update.message.reply_text("🔍 Checking for ORB breakout signals...")

            # Trigger the ORB signal detection
            event = {FIELD_TYPE: EVENT_TYPE_ORB_STRATEGY}
            self.subject.notify(event)

        except Exception as e:
            logger.error(f"Error in check_breakout: {e}", exc_info=True)
            update.message.reply_text(f"Error: {str(e)}")

    def cancel_order(self, update, context):
        """Handle /cancel [order_id] command - Cancel an IB order"""
        try:
            # Check if order ID was provided
            if not context.args:
                update.message.reply_text("Usage: /cancel ORDER_ID")
                return

            # Parse order ID
            try:
                order_id = int(context.args[0])
            except ValueError:
                update.message.reply_text("❌ Invalid order ID. Must be a number.")
                return

            # Cancel the order
            ib_client = self.application_context.client
            ib_client.cancel_stock_order(order_id)

            update.message.reply_text(f"✅ Cancel request sent for order {order_id}")

        except Exception as e:
            logger.error(f"Error in cancel_order: {e}", exc_info=True)
            update.message.reply_text(f"❌ Error cancelling order: {str(e)}")

    def reset_positions(self, update, context):
        """Handle /reset command - Delete all positions from database"""
        try:
            # Initialize database manager
            database_manager = StocksDatabaseManager(self.application_context)

            # Delete all positions
            count = database_manager.delete_all_positions()

            update.message.reply_text(f"✅ Reset complete. Deleted {count} positions from database.")
            logger.info(f"User reset database - {count} positions deleted")

        except Exception as e:
            logger.error(f"Error in reset_positions: {e}", exc_info=True)
            update.message.reply_text(f"❌ Error resetting positions: {str(e)}")

    def send_pnl(self, update, context):
        """Handle /pnl command"""
        try:
            # Get data from service
            from src.stocks.services.stocks_strategy_service import StocksStrategyService
            strategy_service = StocksStrategyService(self.application_context)
            positions = strategy_service.get_positions_pnl()

            if not positions:
                update.message.reply_text("No open positions")
                return

            # Format as PrettyTable
            table = PrettyTable(['Symbol', 'Qty', 'P&L', 'Locked'])
            table.align['Symbol'] = 'l'
            table.align['Qty'] = 'r'
            table.align['P&L'] = 'r'
            table.align['Locked'] = 'r'

            total_pnl = 0
            total_locked = 0
            for p in positions:
                # Format qty with +/- based on direction
                qty_str = f"+{p['shares']}" if p['direction'] == 'LONG' else f"-{p['shares']}"
                pnl_str = f"${p['unrealized_pnl']:.2f}"
                locked_str = f"${p['locked_pnl']:.2f}"
                table.add_row([p['symbol'], qty_str, pnl_str, locked_str])
                total_pnl += p['unrealized_pnl']
                total_locked += p['locked_pnl']

            # Add total row
            table.add_row(['---', '---', '---', '---'])
            table.add_row(['TOTAL', '', f"${total_pnl:.2f}", f"${total_locked:.2f}"])

            # Send using v13.5 parse_mode
            emoji = "📈" if total_pnl >= 0 else "📉"
            update.message.reply_text(
                f'{emoji} Open Positions P&L\n<pre>{table}</pre>',
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            logger.error(f"Error in send_pnl: {e}", exc_info=True)
            update.message.reply_text(f"Error: {str(e)}")

    def send_orders(self, update, context):
        """Handle /orders command"""
        try:
            # Get data from service
            from src.stocks.services.stocks_strategy_service import StocksStrategyService
            strategy_service = StocksStrategyService(self.application_context)
            orders = strategy_service.get_open_orders_summary()

            if not orders:
                update.message.reply_text("No open orders")
                return

            # Format as PrettyTable
            table = PrettyTable(['ID', 'Symbol', 'Qty', 'Type'])
            table.align['ID'] = 'r'
            table.align['Symbol'] = 'l'
            table.align['Qty'] = 'r'
            table.align['Type'] = 'l'

            for o in orders:
                # Format qty with +/- based on action
                qty_str = f"+{o['quantity']}" if o['action'] == 'BUY' else f"-{o['quantity']}"
                table.add_row([o['order_id'], o['symbol'], qty_str, o['type']])

            # Send using v13.5 parse_mode
            update.message.reply_text(
                f'📋 Open Orders\n<pre>{table}</pre>',
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            logger.error(f"Error in send_orders: {e}", exc_info=True)
            update.message.reply_text(f"Error: {str(e)}")

    def manual_scan(self, update, context):
        """Handle /scan command - Run pre-market scan on demand"""
        try:
            update.message.reply_text("📊 Starting manual pre-market scan...")

            # Trigger the pre-market scan (synchronous - will complete before returning)
            event = {FIELD_TYPE: EVENT_TYPE_PRE_MARKET_SCAN}
            self.subject.notify(event)

        except Exception as e:
            logger.error(f"Error in manual_scan: {e}", exc_info=True)
            update.message.reply_text(f"Error: {str(e)}")

    def list_candidates(self, update, context):
        """Handle /list command - Show latest scan results"""
        try:
            from datetime import date

            # Get today's date - container is already in PST
            today = date.today()

            # Get candidates from database
            database_manager = StocksDatabaseManager(self.application_context)
            candidates = database_manager.get_candidates(today, selected_only=True)

            if not candidates:
                update.message.reply_text("No scan results for today")
                return

            # Format as PrettyTable with column headers
            table = PrettyTable(['Rank', 'Symbol', 'Change'])
            table.align['Rank'] = 'r'    # Right align rank
            table.align['Symbol'] = 'l'  # Left align symbol
            table.align['Change'] = 'r'  # Right align change

            # Add rows: rank, symbol, pre_market_change
            for candidate in candidates:  # Already limited to top 25 by selected=True
                table.add_row([
                    candidate.rank,
                    candidate.symbol,
                    f"{candidate.pre_market_change:+.1f}%"
                ])

            # Send using HTML formatting
            update.message.reply_text(
                f"<pre>{table}</pre>",
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            logger.error(f"Error in list_candidates: {e}", exc_info=True)
            update.message.reply_text(f"Error: {str(e)}")

    def error(self, update, context):
        """Log Errors caused by Updates - v13.5 pattern"""
        logger.error('Update "%s" caused error "%s"', update, context.error)

    def _send_message(self, message):
        """Send message via Telegram"""
        if not message:
            logger.warning("Empty message provided to Telegram")
            return

        try:
            # Now actually send via Telegram API
            token = self.state_manager.getConfigValue(CONFIG_TELEGRAM_TOKEN)
            chat_id = self.state_manager.getConfigValue(CONFIG_TELEGRAM_CHAT_ID)

            if token and chat_id:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                params = {
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                }
                requests.get(url, params=params)
            else:
                # Fallback to logging if not configured
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

    def send_margins(self, update, context):
        """Handle /margin command - show cached margin requirements"""
        try:
            # Get data from service layer
            from src.stocks.services.stocks_strategy_service import StocksStrategyService
            strategy_service = StocksStrategyService(self.application_context)
            margins = strategy_service.get_margin_requirements()

            if not margins:
                update.message.reply_text("No margin data available")
                return

            # Format as PrettyTable
            table = PrettyTable(['Symbol', 'Margin/Share', 'Type'])
            table.align['Symbol'] = 'l'
            table.align['Margin/Share'] = 'r'
            table.align['Type'] = 'c'

            for m in margins:
                margin_str = f"${m['margin_per_share']:.2f}"
                type_str = "Synth" if m['synthetic'] else "Real"
                table.add_row([m['symbol'], margin_str, type_str])

            # Send using existing pattern - HTML with <pre> tag, no header
            update.message.reply_text(
                f'<pre>{table}</pre>',
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            logger.error(f"Error in /margin command: {e}", exc_info=True)
            update.message.reply_text(f"Error: {str(e)}")

    def volume_analysis(self, update, context):
        """Handle /va [symbol] command - analyze volume for symbol"""
        try:
            symbol = None
            if context.args:
                symbol = context.args[0].upper()
            else:
                update.message.reply_text("Usage: /va SYMBOL")
                return

            # Publish volume analysis event through proper event system
            event = {FIELD_TYPE: EVENT_TYPE_VOLUME_ANALYSIS, FIELD_DATA: symbol}
            self.state_manager.subject.notify(event)

        except Exception as e:
            logger.error(f"Error in /va command: {e}", exc_info=True)
            update.message.reply_text(f"Error: {str(e)}")