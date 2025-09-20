
from src.core.observer import Subject, IObserver
from src.core.constants import *
from src import logger
import numpy as np

class State(IObserver):

    def __init__(self, client, subject : Subject, config):
        self.subject = subject
        self.client = client
        subject.subscribe(self)
        self.config = config
        self.contract = None
        self.state = {}

    def get_state(self, key :str):
        if key in self.state:
            return self.state[key]
        
        return None
    
    def set_state(self, key : str, value):
        self.remove_state(key)
        logger.debug(f"setting state {key}")
        self.state[key] = value
    
    def remove_state(self, key):
        if key in self.state:
            logger.debug(f"removing state {key}")
            self.state.pop(key)
    
    def inPosition(self):
        
        orders = self.get_state(FIELD_ORDERS)

        if len(orders) > 0:
            logger.debug("order pending")
            return True
        
        return False
    
    def get_pair_config(self, contract, qty = None):
        
        pair_config = FOREX_PAIRS[self.get_pair(contract)]
        pip_size = pair_config["pip_size"]
        decimal_places = pair_config["decimal_places"]
        mini_lot = pair_config["mini_lot"]
        min_qty = pair_config["min_qty"]

        if qty is not None:
            min_qty = qty
        
        return decimal_places, pip_size, (min_qty * mini_lot)


    def get_pair(self, contract):
        return f"{contract.symbol}.{contract.currency}"
    
    def add_underlying(self, contract):    
        contracts = self.get_state(FIELD_UNDERLYING_CONTRACTS)
        pair_key = self.get_pair(contract)
        contracts[pair_key] = contract
    

    def is_stopped(self):
        return self.config[CONFIG_STOPPED]

    def get_config_value(self, key: str):
        return self.config[key]
    
    def getConfigValue(self, key: str):
        return self.config[key]
    
    def notify(self, observable, *args):

        event_type = args[0][FIELD_TYPE]
        if event_type == EVENT_TYPE_MARKET_OPEN:
            if self.config[CONFIG_MARKET_OPEN]: return
            self.config[CONFIG_MARKET_OPEN] = True
            self.config[CONFIG_STOPPED] = False
            logger.info("market open")
            self.sendTelegramMessage("market open")
        if event_type == EVENT_TYPE_MARKET_CLOSED:
            if not self.config[CONFIG_MARKET_OPEN]: return
            self.config[CONFIG_MARKET_OPEN] = False
            logger.info("market closed")
            self.sendTelegramMessage("market closed")
    
    def sendTelegramMessage(self, message):
        logger.debug(message)
        self.subject.notify({FIELD_TYPE: EVENT_TYPE_TELEGRAM_MESSAGE, 
                             FIELD_MESSAGE: message})
    
    def get_current_data_index(self):
        config = self.config
        symbol = config[CONFIG_SYMBOL]
        df_data = self.get_state(FIELD_DATA)[symbol].copy()
        df_data = df_data.set_index('date')
        return df_data.index[-1]

    def get_current_data_index_by_symbol(self, symbol):
        config = self.config
        df_data = self.get_state(FIELD_DATA)[symbol].copy()
        df_data = df_data.set_index('date')
        return df_data.index[-1]

    def get_current_price(self, contract):

        market_data = self.client.get_market_data(contract)
        if market_data is None: return None
        price = market_data[FIELD_AVG_PRICE]
        if price < 0: return None #market closed
        return price
    
    def log_event(self, event):
        debug = self.config[CONFIG_DEBUG]
        if debug:
            logger.info(event)
            self.sendTelegramMessage(event)
        else:
            logger.info(event)
    
    def log_plot(self, event):
        debug = self.config[CONFIG_DEBUG]
        if debug:
            self.subject.notify(event)

    def get_account_summary_symbol(self):
        symbol = self.getConfigValue(CONFIG_SYMBOL)
        currency = self.getConfigValue(CONFIG_CURRENCY)
        if symbol == "USD":
            return currency
        else:
            return symbol
    
    def get_currency_format(self, symbol):

        table = { "BASE": "${:,.2f}", "USD": "${:,.2f}", "EUR": "€{:,.2f}", "GBP": "£{:,.2f}", "JPY": "¥{:,.2f}", "AUD": "A${:,.2f}", "CHF": "CHF{:,.2f}", "CAD": "C${:,.2f}", "NZD": "NZ${:,.2f}"}

        return table[symbol]
    
    def get_unrealized_pnl(self):
        
        pnl = self.get_state(FIELD_PNL)
        total_pnl = 0
        for key in pnl:
            total_pnl += pnl[key][FIELD_UNREALIZED_PNL]
        
        return total_pnl