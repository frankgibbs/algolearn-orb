from src.core.observer import Subject
from src.core.constants import *
from src import logger


class ApplicationContext:
    """
    Centralized application context that provides access to the database manager
    and state manager. This class serves as a dependency injection container
    and provides a unified interface for accessing core application services.
    """

    def __init__(self, state_manager):
        """
        Initialize the application context with the required dependencies.
        
        Args:
            client: The IB client instance
            subject: The observer subject for event handling
            config: Configuration dictionary
        """
        self._client = state_manager.client
        self._subject = state_manager.subject
        self._config = state_manager.config
        self._state_manager = state_manager
        
    
    @property
    def state_manager(self):
        """
        Get the state manager instance.

        Returns:
            The state manager instance
        """
        return self._state_manager
    
    @property
    def database_manager(self):
        """
        Get the database manager instance.

        Returns:
            The database manager instance
        """
        return self._database_manager

    @database_manager.setter
    def database_manager(self, database_manager):
        """
        Set the database manager instance.

        Args:
            database_manager: The database manager instance to set
        """
        self._database_manager = database_manager
    
    
    @property
    def client(self):
        """
        Get the IB client instance.
        
        Returns:
            The IB client instance
        """
        return self._client
    
    @property
    def subject(self) -> Subject:
        """
        Get the observer subject for event handling.
        
        Returns:
            Subject: The observer subject
        """
        return self._subject
    
    @property
    def config(self):
        """
        Get the configuration dictionary.
        
        Returns:
            dict: The configuration dictionary
        """
        return self._config
    
    def get_config_value(self, key: str):
        """
        Get a configuration value by key.
        
        Args:
            key (str): The configuration key
            
        Returns:
            The configuration value
        """
        return self._config.get(key)
    
    def notify(self, event):
        """
        Send a notification event through the subject.
        
        Args:
            event (dict): The event to notify
        """
        self._subject.notify(event)
    
    
    def is_stopped(self):
        """
        Check if the algorithm is stopped.
        
        Returns:
            bool: True if stopped, False otherwise
        """
        return self._state_manager.is_stopped()
    
    def get_unrealized_pnl(self):
        """
        Get the total unrealized PnL.
        
        Returns:
            float: The total unrealized PnL
        """
        return self._state_manager.get_unrealized_pnl()
    
    def send_telegram_message(self, message: str):
        """
        Send a telegram message.
        
        Args:
            message (str): The message to send
        """
        self._state_manager.sendTelegramMessage(message)
    
    def log_event(self, event: str):
        """
        Log an event.
        
        Args:
            event (str): The event to log
        """
        self._state_manager.log_event(event)
    
    def get_returns(self):
        """
        Get trading returns data.
        
        Returns:
            DataFrame: Returns data
        """
        return self._database_manager.getReturns()
    
    def get_orders_by_status(self, status: str):
        """
        Get orders by status.
        
        Args:
            status (str): The status to filter by
            
        Returns:
            DataFrame: Orders with the specified status
        """
        return self._database_manager.getOrderByStatus(status)
    

    def update_stop_price(self, order_id: int, stop_price: float):
        """
        Update the stop price for an order.
        
        Args:
            order_id (int): The order ID
            stop_price (float): The new stop price
        """
        self._database_manager.update_stop_price(order_id, stop_price)
    
    
    def get_currency_format(self, symbol: str):
        """
        Get the currency format for a symbol.
        
        Args:
            symbol (str): The currency symbol
            
        Returns:
            str: The currency format string
        """
        return self._state_manager.get_currency_format(symbol)
    
    def get_pending_trades(self):
        """
        Get all pending trades directly from the database.
        Pending trades are orders that have been submitted but not yet filled.
        
        Returns:
            list: List of Trade objects with status 'PENDING'
        """
        return self._database_manager.get_pending_trades()
    
    def get_open_trades(self):
        """
        Get all open trades directly from the database.
        Open trades are filled orders that are currently active positions.
        
        Returns:
            list: List of Trade objects with status 'OPEN'
        """
        return self._database_manager.get_open_trades()
