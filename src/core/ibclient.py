from src.core.observer import Subject
from src.core.constants import *
from ibapi.client import EClient
from ibapi.ticktype import * 
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract, ContractDetails, ComboLeg
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.order_cancel import OrderCancel
from pytz import timezone
import time
from decimal import Decimal
from random import randint
from time import sleep
import threading
from typing import Optional, Dict, Any
from src.core.utility_functions import generate_candlestick_chart
from src import logger

from datetime import datetime, timedelta
from ibapi.order_cancel import OrderCancel
import pandas as pd

class IBClient(EWrapper, EClient):

    def __init__(self, subject : Subject, config):
        EClient.__init__(self, wrapper = self)
        self.subject = subject
        self.requestId = 1
        self.request_map = {}
        self.request_callback_map = {}
        self.pnl_requests = {}
        self.config = config
        self.ignored_events = { 2107, 2106, 2105}
        self.disconnect_events = { 1100, 504}
        self.connect_events = { 2107, 2106, 2158, 2104}
        self.next_valid_order_id = 0
        self.max_sql_order_id = 0
        self.history_counter = 0
        
        self.orders = {}
        self.market_data = {}
        self.pair_balance = {}
        self.history = {}
        self.contract_details = {}

        self.market_data_received_event = threading.Event()
        self.pair_balance_received_event = threading.Event()
        self.history_received_event = threading.Event()
        self.contract_details_received_event = threading.Event()
        # Add for executions
        self.fills_received_event = threading.Event()
        self.fills = {}
        
        # Add for order submission with margin details
        self.order_submission_event = threading.Event()
        self.submitted_order_details = {}
        
        # Add for next order ID requests
        self.next_order_id_event = threading.Event()
        
        # Add for open orders requests
        self.open_orders_received_event = threading.Event()
        
        # Add for completed orders requests
        self.completed_orders_received_event = threading.Event()
        
        # Add for options data
        self.option_chains = {}
        self.option_chains_received_event = threading.Event()
        self.option_quotes = {}
        self.option_quotes_received_event = threading.Event()
        self.option_request_ids = set()  # Track option quote requests for error handling
        self.scanner_results = {}
        self.scanner_received_event = threading.Event()
        self.scanner_params_received_event = threading.Event()
        self.scanner_params_xml = None
        self.fundamental_data = {}
        self.fundamental_received_event = threading.Event()

        logger.info(config)

    def check_connection(self):
        sleep(randint(1,5))
        self.get_next_order_id()
    
    def get_next_request_id(self):
        self.requestId += 1
        return self.requestId
    
    def do_connect(self):
     
        try:
            self.disconnect()
        except Exception as e:
            pass

        try:
            logger.info(f"connecting to {self.config[CONFIG_HOST]} on port {self.config[CONFIG_PORT]}")
            self.connect(self.config[CONFIG_HOST], self.config[CONFIG_PORT], self.config[CONFIG_CLIENT_ID])    
        except Exception as e:
            logger.exception(e)
            return
        
        time.sleep(5)
        self.get_next_order_id()

        #self.reqAccountUpdates(True, self.config[CONFIG_ACCOUNT])
        #self.reqPositions()

        x = threading.Thread(target=self.run)
        x.start()
  
    def error(self, reqId, errorCode: int, errorString: str, advancedOrderRejectJson = ""):
        super().error(reqId, errorCode, errorString, advancedOrderRejectJson)
        
        if errorCode in self.disconnect_events:
            if self.config[CONFIG_CONNECTED]:
                self.config[CONFIG_CONNECTED] = False
                self.subject.addToQueue({FIELD_TYPE: EVENT_TYPE_DISCONNECTED})
                return


        if errorCode in self.connect_events:
            if not self.config[CONFIG_CONNECTED]:
                self.config[CONFIG_CONNECTED] = True
                self.subject.addToQueue({FIELD_TYPE: EVENT_TYPE_CONNECTED})
                return
        

        
        # Handle "No security definition" errors for options (error code 200)
        if errorCode == 200 and reqId in self.option_request_ids:
            logger.info(f"Invalid option strike detected for reqId {reqId}: {errorString}")
            self.market_data[reqId] = {'invalid': True, 'error': errorString}
            self.market_data_received_event.set()
            self.option_request_ids.discard(reqId)
            return
            
        # Handle errors for order submission
        if reqId in self.submitted_order_details:
            logger.error(f"ERROR CALLBACK: Order submission {reqId} failed: {errorCode} - {errorString}")
            # Set the event to unblock the waiting thread, but leave the data as None
            self.order_submission_event.set()
        
        #print("Error: ", reqId, " ", errorCode, " ", errorString)
        
    def get_historic_data(self, contract, history_duration, history_bar_size,timeout: int = 10, whatToShow = "MIDPOINT") -> Optional[Dict[str, Any]]:
        """
        Get historical data for a contract

        Args:
            contract: Contract object
            history_duration: Duration string (e.g., "60 M")
            history_bar_size: Bar size (e.g., "1 min")
            timeout: Timeout in seconds
            whatToShow: Data type (e.g., "MIDPOINT", "TRADES")

        Returns:
            DataFrame with historical data

        Raises:
            TimeoutError: If unable to get data within timeout
        """
        request_id = self.get_next_request_id()
        pair = f"{contract.symbol}.{contract.currency}"
        self.history_received_event.clear()

        self.history[request_id] = pd.DataFrame()

        self.reqHistoricalData(request_id, contract, "", history_duration, history_bar_size, whatToShow , 1, 1, True, [])

        if self.history_received_event.wait(timeout=timeout):
            result = self.history[request_id]
            self.history.pop(request_id)
            return result
        else:
            raise TimeoutError(f"Timeout waiting for history data for {contract.symbol}-{contract.conId}")

    def historicalData(self, reqId:int, bar):
        super().historicalData(reqId, bar)
        #print("HistoricalData. ReqId:", reqId, "BarData.", bar)
        
        if " US/Eastern" in bar.date:
            the_date = datetime.strptime(bar.date.replace(' US/Eastern', ''), '%Y%m%d %H:%M:%S')
        elif " PST8PDT" in bar.date:
            the_date = datetime.strptime(bar.date.replace(' PST8PDT', ''), '%Y%m%d %H:%M:%S')
        else:
            # Handle dates without timezone (common for stocks)
            if len(bar.date) == 8 and bar.date.isdigit():
                # Daily bars: "20250916"
                the_date = datetime.strptime(bar.date, '%Y%m%d')
            elif ' ' in bar.date:
                # Intraday bars without timezone: "20250916 10:30:00"
                the_date = datetime.strptime(bar.date, '%Y%m%d %H:%M:%S')
            else:
                # Fallback: try as date only
                the_date = datetime.strptime(bar.date, '%Y%m%d')

        bar = {
            "date": the_date,
            "open": bar.open,
            "high": bar.high,
            "low" : bar.low,
            "close": bar.close,
            "volume": bar.volume
        }
        if bar["volume"] == -1:
            bar["volume"] = 0

        # Ensure volume is numeric (int) for mplfinance compatibility
        bar["volume"] = int(bar["volume"])
       
        self.history[reqId] = self.history[reqId].append(bar, ignore_index=True)

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        super().historicalDataEnd(reqId, start, end)
        self.history_received_event.set()

    def get_contract_details(self, contract, timeout: int = 10):
        request_id = self.get_next_request_id()
        self.contract_details_received_event.clear()
        self.contract_details[request_id] = contract

        self.reqContractDetails(request_id, contract)

        if self.contract_details_received_event.wait(timeout=timeout):
            contract = self.contract_details[request_id]
            self.contract_details.pop(request_id)
            return contract
        else:
            logger.info(f"Timeout waiting for contract details for {contract.symbol}-{contract.conId}")
            return None


    def contractDetails(self, reqId: int, contractDetails: ContractDetails):
        super().contractDetails(reqId, contractDetails)

        contract = contractDetails.contract
        self.contract_details[reqId] = contractDetails.contract
        self.contract_details_received_event.set()
                 

    def securityDefinitionOptionParameter(self, reqId: int, exchange: str,
                                               underlyingConId: int, tradingClass: str, multiplier: str,
                                               expirations, strikes):
        super().securityDefinitionOptionParameter(reqId, exchange,
                                                       underlyingConId, tradingClass, multiplier, expirations, strikes)
        
        # Update the pre-initialized option chain data (thread-blocking pattern)
        if reqId in self.option_chains:
            # ACCUMULATE data instead of replacing it (IB sends multiple callbacks)
            logger.info(f"Options data callback for reqId {reqId}, exchange {exchange}: {len(expirations)} expirations, {len(strikes)} strikes")
            logger.info(f"  Exchange: {exchange}, TradingClass: {tradingClass}, Multiplier: {multiplier}")
            logger.info(f"  Sample expirations from this callback: {list(expirations)[:5] if expirations else 'None'}")
            logger.info(f"  Sample strikes from this callback: {list(strikes)[:10] if strikes else 'None'}")
            
            # Convert to sets and accumulate
            self.option_chains[reqId]['expirations'].update(expirations)
            self.option_chains[reqId]['strikes'].update(strikes)
            self.option_chains[reqId]['tradingClass'] = tradingClass
            self.option_chains[reqId]['multiplier'] = multiplier
            
            # Log accumulation progress
            total_expirations = len(self.option_chains[reqId]['expirations'])
            total_strikes = len(self.option_chains[reqId]['strikes'])
            logger.info(f"Accumulated totals for reqId {reqId}: {total_expirations} expirations, {total_strikes} strikes")
    
    def placeBracketOrder(self, action:str, quantity:Decimal, 
                        limitPrice:float, takeProfitLimitPrice:float, 
                        stopLossPrice:float, contract: Contract):
        
        parentOrderId = self.next_valid_order_id

        #This will be our main or "parent" order
        parent = Order()
        parent.orderId = parentOrderId
        parent.action = action
        parent.orderType = "LMT"
        parent.totalQuantity = quantity
        parent.lmtPrice = limitPrice
        #parent.goodTillDate = (datetime.now() + timedelta(minutes = self.config[CONFIG_CAN_PENDING_ORDER_AFTER])).strftime("%Y%m%d-%H:%M:%S")
        #logger.info(f"goodTillDate: {parent.goodTillDate}")
        #The parent and children orders will need this attribute set to False to prevent accidental executions.
        #The LAST CHILD will have it set to True, 
        parent.transmit = False

        takeProfit = Order()
        takeProfit.orderId = parent.orderId + 1
        takeProfit.action = "SELL" if action == "BUY" else "BUY"
        takeProfit.orderType = "LMT"
        takeProfit.totalQuantity = quantity
        takeProfit.lmtPrice = takeProfitLimitPrice
        takeProfit.parentId = parentOrderId
        takeProfit.transmit = False

        stopLoss = Order()
        stopLoss.orderId = parent.orderId + 2
        stopLoss.action = "SELL" if action == "BUY" else "BUY"
        stopLoss.orderType = "STP"
        #Stop trigger price
        stopLoss.auxPrice = stopLossPrice
        stopLoss.totalQuantity = quantity
        stopLoss.parentId = parentOrderId
        #In this case, the low side order will be the last child being sent. Therefore, it needs to set this attribute to True 
        #to activate all its predecessors
        stopLoss.transmit = True
        
        bracket = [parent, takeProfit, stopLoss]
        
        for o in bracket:
            o.tif = "DAY"
            o.eTradeOnly = False
            o.firmQuoteOnly = False
            self.placeOrder(o.orderId, contract, o)

        event = {FIELD_TYPE: EVENT_TYPE_TRADE_PENDING,
                FIELD_ORDER: parent,
                FIELD_CONTRACT: contract}
        self.subject.addToQueue(event)

    def place_order(self, order : Order, contract : Contract, flattening_order = False):
        
        if order.orderId == 0:
            order.orderId = self.next_valid_order_id
        order.transmit = True
        self.placeOrder(order.orderId, contract, order)
    
    def submitOrder(self, orderId: int, contract: Contract, order: Order, timeout: int = 10):
        """
        Submit an order and wait for order details including margin information.
        
        Args:
            orderId: Order ID
            contract: Contract object
            order: Order object  
            timeout: Timeout in seconds
            
        Returns:
            Dict containing order details including margin info, or None if failed
        """
        # Clear previous submission data and event
        self.order_submission_event.clear()
        self.submitted_order_details.clear()
        
        # Pre-populate to signal we're expecting this order ID
        self.submitted_order_details[orderId] = None
        
        # Place the order
        self.placeOrder(orderId, contract, order)
        
        # Wait for openOrder callback
        if self.order_submission_event.wait(timeout):
            order_details = self.submitted_order_details.get(orderId)
            if order_details:
                return order_details
            else:
                logger.error(f"Order details not found for {orderId}")
                return None
        else:
            logger.info(f"Timeout waiting for order submission details for {orderId}")
            return None

    def get_open_orders(self):
        """
        Get all open orders from the IBKR API.
        
        Returns:
            Dict containing all open orders, or None if error
        """
        
        self.open_orders_received_event.clear()
        self.orders.clear()
        self.reqOpenOrders()
        self.open_orders_received_event.wait(timeout=10)
        return self.orders

    def get_order_by_id(self, order_id: int, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific order by order ID (only orders from this client).
        
        Args:
            order_id: The order ID to search for
            timeout: Timeout in seconds
            
        Returns:
            Dict containing order information, or None if not found
        """
          
        # Reset search state
        self.open_orders_received_event.clear()
        self.orders.clear()
        
        # Request only orders from this client ID
        self.reqOpenOrders()
        
        # Wait for the orders to be received
        if self.open_orders_received_event.wait(timeout=timeout):
            # Check if the target order was found
            if order_id in self.orders:
                return self.orders[order_id]
        else:
            logger.info(f"Timeout waiting for orders")
            return None
        
        self.completed_orders_received_event.clear()
        self.orders.clear()
        self.reqCompletedOrders(True)
        
        if self.completed_orders_received_event.wait(timeout=timeout):
            # Check if the target order was found
            if order_id in self.orders:
                return self.orders[order_id]
        else:
            logger.info(f"Timeout waiting for orders")
            return None
        
        return None
    
    def openOrder(self, orderId: int, contract: Contract, order: Order, orderState):
        """Callback when an open order is received."""
        super().openOrder(orderId, contract, order, orderState)
        

                
        # Helper function to safely convert margin values to float
        def safe_float(value, default=0.0):
            try:
                return float(value) if value not in ['N/A', None, '', 'UNSET'] else default
            except (ValueError, TypeError):
                return default
        
        # Create order details with margin information
        order_details = {
            'orderId': orderId,
            'symbol': contract.symbol,
            'secType': contract.secType,
            'exchange': contract.exchange,
            'action': order.action,
            'totalQuantity': order.totalQuantity,
            'orderType': order.orderType,
            'lmtPrice': order.lmtPrice,
            'auxPrice': order.auxPrice,
            'timeInForce': order.tif,
            'orderState': orderState.status,
            'commission': safe_float(orderState.commission),
            'initMarginBefore': safe_float(orderState.initMarginBefore),    # Account margin before this order
            'initMarginAfter': safe_float(orderState.initMarginAfter),      # Account margin after this order  
            'initMarginChange': safe_float(orderState.initMarginChange),    # Margin impact of THIS ORDER
            'maintMarginBefore': safe_float(orderState.maintMarginBefore),
            'maintMarginAfter': safe_float(orderState.maintMarginAfter), 
            'maintMarginChange': safe_float(orderState.maintMarginChange),   # Maintenance margin for THIS ORDER
            'contract': contract,
            'order': order
        }
        
        # Store in orders dict for general access
        self.orders[orderId] = order_details
        
        # Check if this order was submitted via submitOrder and we're waiting for it
        if orderId in self.submitted_order_details:
            logger.info(f"Order {orderId} details received for submitOrder - margin change: {orderState.initMarginChange}")
            self.submitted_order_details[orderId] = order_details
            self.order_submission_event.set()

    def openOrderEnd(self):
        """Callback when all open orders have been received."""
        super().openOrderEnd()
        self.open_orders_received_event.set()

    def completedOrder(self, contract: Contract, order: Order, orderState):
        """Callback when an open order is received."""
        super().completedOrder(contract, order, orderState)
        
        self.orders[order.orderId] = {
            'orderId': order.orderId,
            'symbol': contract.symbol,
            'secType': contract.secType,
            'exchange': contract.exchange,
            'action': order.action,
            'totalQuantity': order.totalQuantity,
            'orderType': order.orderType,
            'lmtPrice': order.lmtPrice,
            'auxPrice': order.auxPrice,
            'timeInForce': order.tif,
            'orderState': orderState.status,
            'commission': orderState.commission,
            'contract': contract,
            'order': order
        }

    def completedOrdersEnd(self):
        """Callback when all completed orders have been received."""
        super().completedOrdersEnd()
        self.completed_orders_received_event.set()

    def get_market_data(self, contract, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        Get current bid/ask quote for a forex pair.
        
        Args:
            contract: Contract object
            timeout: Timeout in seconds
            
        Returns:
            Dict containing bid, ask, and size information, or None if error
        """
      
        # Get unique request ID
        req_id = self.get_next_request_id()
        decimal_places = FOREX_PAIRS[f"{contract.symbol}.{contract.currency}"]["decimal_places"]
        logger.debug(f"Requesting market data for {contract.symbol}-{contract.currency}")
        
        # Reset state
        self.market_data_received_event.clear()
        if req_id in self.market_data:
            del self.market_data[req_id]
        
        # Request market data snapshot
        self.reqMktData(
            reqId=req_id,
            contract=contract,
            genericTickList="",  # Empty for basic bid/ask
            snapshot=True,       # Get snapshot, not streaming
            regulatorySnapshot=False,
            mktDataOptions=[]
        )
        
        # Wait for data to be received
        if self.market_data_received_event.wait(timeout=timeout):
            if req_id in self.market_data:
                quote_data = self.market_data[req_id].copy()
                quote_data['symbol'] = contract.symbol
                
                if 'bid' in quote_data and 'ask' in quote_data:
                    quote_data[FIELD_AVG_PRICE] = round((quote_data['ask'] + quote_data['bid']) / 2, decimal_places)
                return quote_data
            else:
                logger.error(f"No market data received for {contract.symbol}.{contract.currency}")
                return None
        else:
            logger.error(f"Timeout waiting for market data for {contract.symbol}.{contract.currency}")
            return None

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib):
        """Callback when price data is received."""
        super().tickPrice(reqId, tickType, price, attrib)
        
        if reqId not in self.market_data:
            self.market_data[reqId] = {}
        
        # Map tick types to readable names
        if tickType == 1:  # Bid price
            self.market_data[reqId]['bid'] = price
        elif tickType == 2:  # Ask price
            self.market_data[reqId]['ask'] = price
        elif tickType == 4:  # Last price
            self.market_data[reqId]['last'] = price

    def tickSize(self, reqId: int, tickType: int, size: float):
        """Callback when size data is received."""
        super().tickSize(reqId, tickType, size)
        
        if reqId not in self.market_data:
            self.market_data[reqId] = {}
        
        # Map tick types to readable names
        if tickType == 0:  # Bid size
            self.market_data[reqId]['bid_size'] = size
            logger.debug(f"Bid size: {size}")
        elif tickType == 3:  # Ask size
            self.market_data[reqId]['ask_size'] = size
            logger.debug(f"Ask size: {size}")
        elif tickType == 5:  # Last size
            self.market_data[reqId]['last_size'] = size
    
    def tickSnapshotEnd(self, reqId: int):
        """Callback when snapshot is complete."""
        super().tickSnapshotEnd(reqId)
        self.market_data_received_event.set()

    def get_pair_balance(self, symbol : str):
        """
        Get account balance for a currency

        Args:
            symbol: Currency symbol (e.g., "USD")

        Returns:
            Float balance amount

        Raises:
            TimeoutError: If unable to get balance within timeout
        """
        self.pair_balance_received_event.clear()
        self.pair_balance.clear()
        self.pair_balance[symbol] = 0
        if symbol is None or symbol == "USD":
            request = "$LEDGER"
        else:
            request = f"$LEDGER:{symbol}"

        request_id = self.get_next_request_id()
        self.reqAccountSummary(request_id, "All", request)

        if self.pair_balance_received_event.wait(timeout=10):
            return self.pair_balance[symbol]
        else:
            raise TimeoutError(f"Timeout waiting for pair balance for {symbol}")
    
    def accountSummary(self, reqId: int, account: str, tag: str, value: str,
                           currency: str):
        super().accountSummary(reqId, account, tag, value, currency)
        
        if tag != "TotalCashBalance": return

        if currency == "BASE":
            self.pair_balance["USD"] = float(value)
        else:
            self.pair_balance[currency] = float(value)

    def accountSummaryEnd(self, reqId: int):
        super().accountSummaryEnd(reqId)
        
        self.cancelAccountSummary(reqId)

        self.pair_balance_received_event.set()
 
    def startPnl(self, contract : Contract):

        if contract.conId in self.pnl_requests:
            logger.info(f"pnl for {contract.conId} already started")
            return
        
        request_id = self.get_next_request_id()
        self.request_map[request_id] = contract
        self.request_map[contract.conId] = request_id
        logger.info(f"starting pnl for request id: {request_id}")
        self.pnl_requests[contract.conId] = contract

        self.reqPnLSingle(request_id, self.config[CONFIG_ACCOUNT], "", contract.conId);
        #logger.info(f"tickPrice. reqId: {reqId}, tickType: {TickTypeEnum.to_str(tickType)}, price: {price}, attribs: {attrib}")
    
    def updatePortfolio(self, contract: Contract, position: Decimal,
                             marketPrice: float, marketValue: float,
                             averageCost: float, unrealizedPNL: float,
                             realizedPNL: float, accountName: str):
        super().updatePortfolio(contract, position, marketPrice, marketValue,
                                     averageCost, unrealizedPNL, realizedPNL, accountName)
        
        print("UpdatePortfolio.", "Symbol:", contract.symbol, "SecType:", contract.secType, "Exchange:",
                   contract.exchange, "Position:", position, "MarketPrice:", marketPrice,
                   "MarketValue:", marketValue, "AverageCost:", averageCost,
                  "UnrealizedPNL:", unrealizedPNL, "RealizedPNL:", realizedPNL,
                  "AccountName:", accountName)
    
    def get_next_order_id(self, timeout: int = 10):
        """
        Get the next valid order ID synchronously using thread event pattern
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            Next valid order ID or None if timeout
        """
        # Clear the event and request new order IDs
        self.next_order_id_event.clear()
        self.reqIds(-1)
        
        # Wait for the nextValidId callback to set the event
        if self.next_order_id_event.wait(timeout=timeout):
            return self.next_valid_order_id
        else:
            logger.info(f"Timeout waiting for next order ID")
            return None
    
    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)

        self.next_valid_order_id = orderId      
        # Set the event to signal order ID received
        self.next_order_id_event.set()

    def position(self, account: str, contract: Contract, position: Decimal,
                      avgCost: float):
        
        super().position(account, contract, position, avgCost)
        
        if contract.symbol != self.config[FIELD_SYMBOL]:
            return
        
        logger.info(f"position {position} for {contract.symbol}-{contract.conId} account {account} avgCost {avgCost}" )       
            
        """ 
        event = { FIELD_TYPE: EVENT_TYPE_POSITION_UPDATE,
                    FIELD_QTY: position,
                    FIELD_CONTRACT: contract,
                    FIELD_AVG_PRICE: avgCost}

            self.subject.notify(event)
            """    
    
    def tickOptionComputation(self, reqId, tickType , tickAttrib: int, impliedVol: float, delta: float, optPrice: float, pvDividend: float, gamma: float, vega: float, theta: float, undPrice: float):
        
        # Initialize market_data if needed
        if reqId not in self.market_data:
            self.market_data[reqId] = {}
        
        # Only update Greeks if we have non-None values (preserve existing good data)
        if impliedVol is not None:
            self.market_data[reqId]['iv'] = impliedVol
        if delta is not None:
            self.market_data[reqId]['delta'] = delta
        if gamma is not None:
            self.market_data[reqId]['gamma'] = gamma
        if theta is not None:
            self.market_data[reqId]['theta'] = theta
        if vega is not None:
            self.market_data[reqId]['vega'] = vega
        if optPrice is not None:
            self.market_data[reqId]['option_price'] = optPrice
        if undPrice is not None:
            self.market_data[reqId]['underlying_price'] = undPrice
        
        # Always update tick_type to track which callback we got
        self.market_data[reqId]['tick_type'] = tickType

    def get_fills_by_order_id(self, order_id, timeout=10):
        """
        Fetches and aggregates all fills for a given order ID.
        Returns a list with a single dict (or empty list if not found or total_shares is 0).
        """
        self.fills_received_event.clear()
        self.fills.clear()

        from ibapi.execution import ExecutionFilter
        exec_filter = ExecutionFilter()
        exec_filter.orderId = order_id

        self.reqExecutions(self.get_next_request_id(), exec_filter)

        if self.fills_received_event.wait(timeout=timeout):
            fills = self.fills.get(order_id, [])
            if not fills:
                return None 
            # Aggregate
            total_shares = sum(float(f['shares']) for f in fills)
            if total_shares == 0:
                return None
            avg_price = (
                sum(float(f['shares']) * float(f['price']) for f in fills) / total_shares
            )
            first_fill_time = min(f['time'] for f in fills)
            last_fill_time = max(f['time'] for f in fills)
            first_fill = fills[0]
            agg = {
                'orderId': order_id,
                'symbol': first_fill['symbol'],
                'side': first_fill['side'],
                'total_shares': total_shares,
                'lmtPrice': avg_price,
                'first_fill_time': first_fill_time,
                'last_fill_time': last_fill_time,
                'fills': fills,  # Optionally include raw fills
            }
            logger.info(f"fills for order {order_id}: {agg}")
            return agg
        else:
            logger.info(f"Timeout waiting for fills for order {order_id}")
            return None

    def execDetails(self, reqId, contract, execution):
        super().execDetails(reqId, contract, execution)
        fills = self.fills.setdefault(execution.orderId, [])
        fills.append({
            'orderId': execution.orderId,
            'symbol': contract.symbol,
            'side': execution.side,
            'shares': execution.shares,
            'price': execution.price,
            'time': execution.time,
            'execId': execution.execId,
            'permId': execution.permId,
            'clientId': execution.clientId,
            'accountNumber': execution.acctNumber,
        })

    def execDetailsEnd(self, reqId):
        super().execDetailsEnd(reqId)
        self.fills_received_event.set()

    def orderState(self, reqId: int, state: OrderState):
        super().orderState(reqId, state)
        logger.info(f"Order state: {reqId} {state}")

    def get_stock_contract(self, symbol, exchange="SMART", currency="USD"):
        """Create a stock contract for options chain requests"""
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = exchange
        contract.currency = currency
        return contract

    def get_options_chain(self, symbol, timeout=30):
        """Get options chain for a stock symbol"""
        request_id = self.get_next_request_id()
        
        # Create stock contract
        stock_contract = self.get_stock_contract(symbol)
        
        # Get contract details first to populate conId
        logger.debug(f"Fetching contract details for {symbol}")
        contract_details = self.get_contract_details(stock_contract)
        if not contract_details:
            logger.error(f"Could not get contract details for {symbol}")
            return None
        
        # Now we have the proper conId
        underlying_con_id = contract_details.conId
        
        # Clear previous data and event
        self.option_chains_received_event.clear()
        self.option_chains[request_id] = {
            'symbol': symbol,
            'expirations': set(),  # Use set for accumulation
            'strikes': set(),      # Use set for accumulation
            'multiplier': None,
            'tradingClass': None,
            'underlyingConId': underlying_con_id
        }
        
        logger.info(f"Requesting options chain for {symbol} with conId {underlying_con_id} (req_id: {request_id})")
        
        # Request option parameters with the valid conId
        self.reqSecDefOptParams(request_id, symbol, "", "STK", underlying_con_id)
        
        if self.option_chains_received_event.wait(timeout=timeout):
            chain_data = self.option_chains.get(request_id)
            self.option_chains.pop(request_id, None)
            return chain_data
        else:
            logger.error(f"Timeout waiting for options chain for {symbol}")
            self.option_chains.pop(request_id, None)
            return None

    def securityDefinitionOptionParameterEnd(self, reqId: int):
        """Called when option parameter request is complete"""
        super().securityDefinitionOptionParameterEnd(reqId)
        logger.debug(f"Options chain data complete for request {reqId}")
        self.option_chains_received_event.set()

    def get_option_contract(self, symbol, expiry, strike, right, exchange="SMART"):
        """Create an option contract"""
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "OPT"
        contract.exchange = exchange
        contract.currency = "USD"
        contract.lastTradeDateOrContractMonth = expiry
        contract.strike = strike
        contract.right = right  # "P" for put, "C" for call
        contract.multiplier = "100"
        return contract

    def get_option_quote(self, symbol, expiry, strike, right="P", timeout=20):
        """Get real-time quote for specific option"""
        request_id = self.get_next_request_id()
        
        # Create option contract
        option_contract = self.get_option_contract(symbol, expiry, strike, right)
        
        # Clear previous data and event
        self.market_data_received_event.clear()
        if request_id in self.market_data:
            del self.market_data[request_id]
        
        logger.info(f"Requesting option quote for {symbol} {strike}{right} exp:{expiry} (reqId: {request_id})")
        logger.info(f"  Contract details: symbol={option_contract.symbol}, strike={option_contract.strike}, "
                   f"expiry={option_contract.lastTradeDateOrContractMonth}, right={option_contract.right}, "
                   f"exchange={option_contract.exchange}, multiplier={option_contract.multiplier}")
        
        # Track this request ID for error handling
        self.option_request_ids.add(request_id)
        
        # Request market data for option
        self.reqMktData(
            reqId=request_id,
            contract=option_contract,
            genericTickList="",
            snapshot=True,
            regulatorySnapshot=False,
            mktDataOptions=[]
        )
        
        if self.market_data_received_event.wait(timeout=timeout):
            quote_data = self.market_data.get(request_id)
            # Clean up tracking
            self.option_request_ids.discard(request_id)
            if quote_data:
                quote_data['symbol'] = symbol
                quote_data['strike'] = strike
                quote_data['expiry'] = expiry
                quote_data['right'] = right
            return quote_data
        else:
            logger.error(f"Timeout waiting for option quote for {symbol} {strike}{right}")
            # Clean up tracking on timeout
            self.option_request_ids.discard(request_id)
            return None

    def get_option_greeks(self, symbol, expiry, strike, right="P", timeout=25):
        """Get Greeks (including IV) for a specific option"""
        request_id = self.get_next_request_id()
        
        # Create option contract
        option_contract = self.get_option_contract(symbol, expiry, strike, right)
        
        # Clear previous data and prepare for Greeks
        self.market_data_received_event.clear()
        if request_id in self.market_data:
            del self.market_data[request_id]
        
        logger.info(f"Requesting Greeks for {symbol} {strike}{right} exp:{expiry} (reqId: {request_id})")
        
        # Request market data with Greeks (tick type 13 includes Greeks)
        self.reqMktData(
            reqId=request_id,
            contract=option_contract,
            genericTickList="13",  # Request Greeks
            snapshot=True,
            regulatorySnapshot=False,
            mktDataOptions=[]
        )
        
        if self.market_data_received_event.wait(timeout=timeout):
            data = self.market_data.get(request_id, {})
            logger.info(f"Greeks data for reqId {request_id}: {data}")
            result = {
                'symbol': symbol,
                'strike': strike,
                'expiry': expiry,
                'right': right,
                **data
            }
            return result
        else:
            logger.error(f"Timeout waiting for Greeks for {symbol} {strike}{right}")
            return None

    def scan_market(self, scan_params, timeout=30):
        """Use IB market scanner to find stocks/options"""
        request_id = self.get_next_request_id()
        
        # Clear previous data
        self.scanner_received_event.clear()
        self.scanner_results[request_id] = []
        
        from ibapi.scanner import ScannerSubscription, ScanData
        
        # Create scanner subscription
        scanner_sub = ScannerSubscription()
        scanner_sub.instrument = scan_params.get("instrument", "STK")
        scanner_sub.locationCode = scan_params.get("locationCode", "STK.US.MAJOR")
        scanner_sub.scanCode = scan_params.get("scanCode", "HIGH_OPT_IMP_VOLAT")
        scanner_sub.numberOfRows = scan_params.get("numberOfRows", 20)
        
        logger.info(f"Starting market scan: {scanner_sub.scanCode}")
        
        # Start scanner subscription
        self.reqScannerSubscription(request_id, scanner_sub, [], [])
        
        if self.scanner_received_event.wait(timeout=timeout):
            results = self.scanner_results.get(request_id, [])
            self.scanner_results.pop(request_id, None)
            # Cancel the subscription
            self.cancelScannerSubscription(request_id)
            return results
        else:
            logger.error(f"Timeout waiting for scanner results")
            self.cancelScannerSubscription(request_id)
            return []

    def get_scanner_parameters(self, timeout=10):
        """Request available scanner parameters from IB"""
        self.scanner_params_received_event.clear()
        self.scanner_params_xml = None

        logger.info("Requesting scanner parameters from IB")
        self.reqScannerParameters()

        if self.scanner_params_received_event.wait(timeout=timeout):
            return self.scanner_params_xml
        else:
            logger.error("Timeout waiting for scanner parameters")
            return None

    def scannerData(self, reqId: int, rank: int, contractDetails, distance: str, benchmark: str, projection: str, legsStr: str):
        """Callback for scanner data"""
        super().scannerData(reqId, rank, contractDetails, distance, benchmark, projection, legsStr)
        
        if reqId not in self.scanner_results:
            self.scanner_results[reqId] = []
        
        # Store scanner result
        self.scanner_results[reqId].append({
            'rank': rank,
            'symbol': contractDetails.contract.symbol,
            'contract': contractDetails.contract,
            'distance': distance,
            'benchmark': benchmark,
            'projection': projection
        })

    def scannerDataEnd(self, reqId: int):
        """Called when scanner data is complete"""
        super().scannerDataEnd(reqId)
        logger.info(f"Scanner data complete for request {reqId}")
        self.scanner_received_event.set()

    def scannerParameters(self, xml: str):
        """Callback that receives scanner parameters XML from IB"""
        super().scannerParameters(xml)
        self.scanner_params_xml = xml
        self.scanner_params_received_event.set()
        logger.info(f"Scanner parameters received, XML length: {len(xml)}")
        # Log first 500 chars to see structure
        logger.info(f"XML preview: {xml[:500]}")

    def get_option_margin(self, symbol, expiry, strike, right="P", quantity=1, timeout=10):
        """Calculate margin requirement for option trade using what-if order"""
        # Create option contract
        option_contract = self.get_option_contract(symbol, expiry, strike, right)
        
        # Create a what-if order for naked put
        order = Order()
        order.action = "SELL"  # Selling puts
        order.orderType = "LMT"
        order.totalQuantity = quantity
        order.lmtPrice = 1.0  # Dummy price for margin calculation
        order.whatIf = True  # This makes it a what-if order for margin calc
        
        # Submit the what-if order
        order_id = self.get_next_order_id()
        if order_id:
            return self.submitOrder(order_id, option_contract, order, timeout)
        else:
            return None

    def get_fundamental_data(self, symbol, report_type="RealtimeRatios", timeout=10):
        """Get fundamental data for a stock"""
        request_id = self.get_next_request_id()
        
        # Create stock contract
        stock_contract = self.get_stock_contract(symbol)
        
        # Clear previous data
        self.fundamental_received_event.clear()
        self.fundamental_data[request_id] = None
        
        logger.debug(f"Requesting fundamental data for {symbol}")
        
        # Request fundamental data
        self.reqFundamentalData(request_id, stock_contract, report_type, [])
        
        if self.fundamental_received_event.wait(timeout=timeout):
            data = self.fundamental_data.get(request_id)
            self.fundamental_data.pop(request_id, None)
            return data
        else:
            logger.error(f"Timeout waiting for fundamental data for {symbol}")
            return None

    def fundamentalData(self, reqId: int, data: str):
        """Callback for fundamental data"""
        super().fundamentalData(reqId, data)
        self.fundamental_data[reqId] = data
        self.fundamental_received_event.set()

    def get_stock_market_data(self, contract, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        Get current bid/ask quote for a stock (not forex)
        
        Args:
            contract: Stock contract object
            timeout: Timeout in seconds
            
        Returns:
            Dict containing bid, ask, and size information, or None if error
        """
        # Get unique request ID
        req_id = self.get_next_request_id()
        # Use 2 decimal places for stocks (no FOREX_PAIRS lookup)
        decimal_places = 2
        logger.debug(f"Requesting stock market data for {contract.symbol}")
        
        # Reset state
        self.market_data_received_event.clear()
        if req_id in self.market_data:
            del self.market_data[req_id]
        
        # Request market data snapshot
        self.reqMktData(
            reqId=req_id,
            contract=contract,
            genericTickList="",  # Empty for basic bid/ask
            snapshot=True,       # Get snapshot, not streaming
            regulatorySnapshot=False,
            mktDataOptions=[]
        )
        
        # Wait for data to be received
        if self.market_data_received_event.wait(timeout=timeout):
            if req_id in self.market_data:
                quote_data = self.market_data[req_id].copy()
                quote_data['symbol'] = contract.symbol
                
                if 'bid' in quote_data and 'ask' in quote_data:
                    quote_data[FIELD_AVG_PRICE] = round((quote_data['ask'] + quote_data['bid']) / 2, decimal_places)
                return quote_data
            else:
                logger.error(f"No market data received for stock {contract.symbol}")
                return None
        else:
            logger.error(f"Timeout waiting for stock market data for {contract.symbol}")
            return None

    def get_stock_price(self, symbol, timeout=10):
        """
        Get current stock price (last/mark price)

        Args:
            symbol: Stock symbol
            timeout: Timeout in seconds

        Returns:
            Float price

        Raises:
            RuntimeError: If unable to get price data
            TimeoutError: If request times out
        """
        # Create stock contract
        stock_contract = self.get_stock_contract(symbol)

        # Get market data using stock-specific method
        quote_data = self.get_stock_market_data(stock_contract, timeout)

        if not quote_data:
            raise RuntimeError(f"Unable to get market data for {symbol}")

        # Try to get last price first, then average of bid/ask
        last_price = quote_data.get('last')
        if last_price and last_price > 0:
            return float(last_price)

        bid = quote_data.get('bid', 0)
        ask = quote_data.get('ask', 0)

        if bid > 0 and ask > 0:
            return float((bid + ask) / 2)
        elif bid > 0:
            return float(bid)
        elif ask > 0:
            return float(ask)
        else:
            raise RuntimeError(f"No valid price found for {symbol} - bid: {bid}, ask: {ask}, last: {last_price}")

    def get_stock_bars(self, symbol, duration_minutes=60, bar_size="1 min", timeout=10):
        """
        Get historical bars for a stock (wrapper around existing get_historic_data)

        Args:
            symbol: Stock symbol
            duration_minutes: Number of minutes to fetch (e.g., 60 for 1 hour)
            bar_size: Bar size (e.g., "1 min", "5 mins")
            timeout: Timeout in seconds

        Returns:
            DataFrame with OHLCV data

        Raises:
            RuntimeError: If no data received or contract invalid
            TimeoutError: If request times out
        """
        if not symbol:
            raise ValueError("symbol is required")

        # Create stock contract
        contract = self.get_stock_contract(symbol)

        # Convert minutes to IB duration string (M = MONTHS, so use seconds)
        duration_str = f"{duration_minutes * 60} S"

        # Use existing method with TRADES data for stocks
        result = self.get_historic_data(contract, duration_str, bar_size, timeout, "TRADES")

        if result is None:
            raise TimeoutError(f"Timeout getting historical data for {symbol}")

        if result.empty:
            raise RuntimeError(f"No historical data received for {symbol}")

        return result

    def place_stock_entry_with_stop(self, symbol, action, quantity, entry_price, stop_price):
        """
        Place ONLY entry and stop orders (NO take profit order)
        Take profit is monitored by position manager, not placed as order

        Args:
            symbol: Stock symbol
            action: "BUY" or "SELL"
            quantity: Number of shares
            entry_price: Limit price for entry (ignored for market orders)
            stop_price: Stop loss price

        Returns:
            Dict with {'parent_order_id': xxx, 'stop_order_id': xxx, 'symbol': xxx}

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If order IDs cannot be obtained
        """
        if not symbol:
            raise ValueError("symbol is required")
        if action not in ["BUY", "SELL"]:
            raise ValueError("action must be BUY or SELL")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if stop_price <= 0:
            raise ValueError("stop_price must be positive")

        # Create stock contract
        contract = self.get_stock_contract(symbol)

        # Get next order IDs - max from IB and DB
        ib_next_id = self.get_next_order_id()
        if ib_next_id is None:
            raise RuntimeError("Could not get next order ID from IB")

        # TODO: Get max order ID from database when database_manager is available
        # For now, just use IB's next ID
        parent_order_id = ib_next_id
        stop_order_id = parent_order_id + 1

        # Create parent order (entry) - MARKET order
        parent = Order()
        parent.orderId = parent_order_id
        parent.action = action
        parent.orderType = "MKT"  # Market order for guaranteed fill
        parent.totalQuantity = quantity
        parent.tif = "DAY"  # Day order
        parent.transmit = False  # Don't send yet

        # Create child stop order
        stop_order = Order()
        stop_order.orderId = stop_order_id
        stop_order.parentId = parent_order_id
        stop_order.action = "SELL" if action == "BUY" else "BUY"  # Opposite action
        stop_order.orderType = "STP"  # Stop market order
        stop_order.auxPrice = stop_price  # Trigger price
        stop_order.totalQuantity = quantity
        stop_order.tif = "DAY"  # Day order
        stop_order.transmit = True  # Send both orders

        logger.info(f"Placing stock orders for {symbol}: {action} {quantity} shares, stop at {stop_price}")

        # Place orders
        self.placeOrder(parent.orderId, contract, parent)
        self.placeOrder(stop_order.orderId, contract, stop_order)

        # Return order IDs immediately (no confirmation wait)
        return {
            'parent_order_id': parent_order_id,
            'stop_order_id': stop_order_id,
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'entry_price': entry_price,
            'stop_price': stop_price
        }

    def modify_stop_order(self, order_id, new_stop_price, timeout=10):
        """
        Modify an existing stop order (for trailing stops)
        Used to implement trailing stop by moving existing stop order

        Args:
            order_id: Stop order ID to modify
            new_stop_price: New stop price
            timeout: Timeout for order lookup

        Returns:
            True if successful

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If order not found, not a stop order, or already filled
        """
        if not order_id:
            raise ValueError("order_id is required")
        if new_stop_price <= 0:
            raise ValueError("new_stop_price must be positive")

        # Get existing order details
        order_details = self.get_order_by_id(order_id, timeout)
        if not order_details:
            raise RuntimeError(f"Order {order_id} not found")

        # Extract order and contract
        existing_order = order_details['order']
        contract = order_details['contract']
        order_state = order_details.get('orderState', 'Unknown')

        # Validate it's actually a stop order
        if existing_order.orderType not in ['STP', 'STP LMT']:
            raise ValueError(f"Order {order_id} is not a stop order (type: {existing_order.orderType})")

        # Check order status (can't modify filled/cancelled orders)
        if order_state in ['Filled', 'Cancelled']:
            raise RuntimeError(f"Cannot modify {order_state} order {order_id}")

        # Modify the stop price
        existing_order.auxPrice = new_stop_price

        logger.info(f"Modifying stop order {order_id} to new stop price: {new_stop_price}")

        # Re-submit with same order ID (this modifies it)
        self.placeOrder(order_id, contract, existing_order)

        return True

    def convert_stop_to_market(self, order_id, timeout=10):
        """
        Convert a stop order to a market order for immediate execution
        Used for time-based exits and EOD closures

        Args:
            order_id: Stop order ID to convert
            timeout: Timeout for order lookup

        Returns:
            True if successful

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If order not found, not a stop order, or already filled
        """
        if not order_id:
            raise ValueError("order_id is required")

        # Get existing order details
        order_details = self.get_order_by_id(order_id, timeout)
        if not order_details:
            raise RuntimeError(f"Order {order_id} not found")

        # Extract order and contract
        existing_order = order_details['order']
        contract = order_details['contract']
        order_state = order_details.get('orderState', 'Unknown')

        # Validate it's actually a stop order
        if existing_order.orderType not in ['STP', 'STP LMT']:
            raise ValueError(f"Order {order_id} is not a stop order (type: {existing_order.orderType})")

        # Check order status (can't modify filled/cancelled orders)
        if order_state in ['Filled', 'Cancelled']:
            raise RuntimeError(f"Cannot modify {order_state} order {order_id}")

        logger.info(f"Converting stop order {order_id} to market order for immediate execution")

        # Convert to market order
        existing_order.orderType = 'MKT'
        existing_order.auxPrice = 0  # Market orders don't have stop price

        # Re-submit with same order ID (this modifies it)
        self.placeOrder(order_id, contract, existing_order)

        return True

    def cancel_stock_order(self, order_id):
        """
        Cancel an order by ID

        Args:
            order_id: Order ID to cancel (required)

        Returns:
            Boolean indicating success

        Raises:
            ValueError: If order_id is invalid
            RuntimeError: If cancel fails
        """
        if not order_id:
            raise ValueError("order_id is REQUIRED")

        try:
            # Create OrderCancel object with default values
            order_cancel = OrderCancel()

            # Call the inherited cancelOrder method from EClient
            self.cancelOrder(order_id, order_cancel)
            logger.info(f"Cancel request sent for order {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            raise RuntimeError(f"Failed to cancel order {order_id}: {e}")

    def get_margin_per_share(self, symbol, timeout=10):
        """
        Get margin requirement per share by testing with 10 shares

        Args:
            symbol: Stock symbol (required)
            timeout: Timeout in seconds

        Returns:
            Float margin requirement per share

        Raises:
            ValueError: If symbol is invalid
            RuntimeError: If margin check fails or returns invalid data
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        # Create what-if order for 10 shares
        contract = self.get_stock_contract(symbol)

        order = Order()
        order.action = "BUY"
        order.orderType = "MKT"
        order.totalQuantity = 10
        order.whatIf = True  # What-if order for margin calc

        order_id = self.get_next_order_id()
        if not order_id:
            raise RuntimeError(f"Could not get order ID for margin check")

        result = self.submitOrder(order_id, contract, order, timeout)

        if not result:
            raise RuntimeError(f"Could not get margin info for {symbol}")

        # Get margin change for 10 shares - NO DEFAULTS
        margin_for_10 = result.get('initMarginChange')
        if margin_for_10 is None or margin_for_10 == 0:
            raise RuntimeError(f"Invalid margin data for {symbol}: {margin_for_10}")

        # Use absolute value since we care about margin requirement regardless of direction
        # Negative = short selling frees up margin, Positive = buying requires margin
        margin_for_10 = abs(margin_for_10)
        margin_per_share = margin_for_10 / 10
        logger.info(f"Margin check for {symbol}: ${margin_for_10:.2f} for 10 shares = ${margin_per_share:.2f} per share")

        return margin_per_share

    def get_stock_bars_extended(self, symbol, duration_days=30, bar_size="15 mins", timeout=10):
        """
        Get historical bars for extended periods using day duration

        Args:
            symbol: Stock symbol
            duration_days: Number of calendar days to fetch
            bar_size: Bar size (e.g., "15 mins", "30 mins")
            timeout: Timeout in seconds

        Returns:
            DataFrame with OHLCV data

        Raises:
            RuntimeError: If no data received or contract invalid
            TimeoutError: If request times out
        """
        if not symbol:
            raise ValueError("symbol is required")
        if duration_days is None or duration_days <= 0:
            raise ValueError("duration_days must be positive")

        # Create stock contract
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        # Use "D" for days instead of "S" for seconds
        duration_str = f"{duration_days} D"

        # Use TRADES data for stocks
        result = self.get_historic_data(contract, duration_str, bar_size, timeout, "TRADES")

        if result is None:
            raise TimeoutError(f"Timeout getting historical data for {symbol}")
        if result.empty:
            raise RuntimeError(f"No historical data received for {symbol}")

        return result

