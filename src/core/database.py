
from src.core.observer import Subject, IObserver
from src.core.constants import *
from src.core.state import State

import pandas as pd

from src import logger

from src import Base

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.core.trade import Trade
# Import options models to register with SQLAlchemy
from src.options.models.option_trade import OptionTrade, ScreeningRun, IVHistory
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import func
class Database(IObserver):

    def __init__(self, application_context):
        
        self.application_context = application_context
        self.subject = application_context.subject
        self.client = application_context.client
        self.state_manager = application_context.state_manager
        self.state_manager.subject.subscribe(self)
        db_file_name = (f"sqlite:///data/forexv4.sqlite")
        self.engine = create_engine(db_file_name)
        Base.metadata.create_all(bind=self.engine)
    
    def _connect(self):
        
        Session = sessionmaker(bind=self.engine)
        session = Session()
        return session

    def getNextOrderId(self):
        session = self._connect()    
        try:
            #rs = session.execute(f"SELECT max( max(id),max(profit_order_id),max(stop_order_id)) as {FIELD_ORDER_ID} from trades")
            rs = session.execute(f"SELECT max( max(id),max(stop_order_id)) as {FIELD_ORDER_ID} from trades")
            values = dict(rs.first())
            return values[FIELD_ORDER_ID]
        finally: 
            session.close()

    def createTrade(self, order, open_trade_index = 0):
        
        session = self._connect()

        try:
            trade = session.query(Trade).get(order.orderId)
            if trade !=  None:
                logger.info(f"trade already created for orderId: {order.orderId}")
                return
            
            trade = Trade()
            trade.id = order.orderId
            trade.quantity = int(order.totalQuantity)
            trade.stop_order_id = order.orderId + 1
            trade.profit_order_id = -1
            trade.direction = order.action
            trade.avg_open_price = 0
            trade.avg_close_price = 0
            trade.net_profit = 0
            trade.net_return = 0
            trade.status = "PENDING"
            trade.open_trade_index = open_trade_index
            
            session.add(trade)
            session.commit()
            logger.debug(trade)
            logger.info(f"trade created for orderId: {order.orderId}")
            
        finally:
            session.close()

    def updateOpenTrade(self, orderId : int, avg_open_price : float, open_trade_index):
         
        session = self._connect()
        try:
            trade = session.query(Trade).get(orderId)
            if trade ==  None:
                logger.error(f"trade not found for orderId: {orderId}")
                return
            
            trade.avg_open_price = avg_open_price
            trade.open_trade_index = open_trade_index
            trade.status = "OPEN"
            session.commit()
            self.state_manager.set_state(FIELD_OPEN_TRADE, trade)
            logger.info(f"trade updated for orderId: {orderId} status: {trade.status}")
        finally:
            session.close()
    
    def updateCanceledTrade(self, orderId):
        
        session = self._connect()
        try:
            trade =  self.get_trade_by_order_id(orderId)
            
            if trade ==  None:
                logger.error(f"trade not found for orderId: {orderId}")
                return
            
            if trade.id != orderId:
                logger.error(f"only cancellation of opening order is allowed to cancel trade")
                return

            trade = session.query(Trade).get(trade.id)
            trade.status = "CANCELLED"
            session.commit()
            self.state_manager.set_state(FIELD_OPEN_TRADE, None)
            logger.info(f"trade canceled for orderId: {orderId} status: {trade.status}")
        finally:
            session.close()
                
    def getReturns(self):

        session = self._connect()
        try:
            rs = session.execute("SELECT strftime('%Y-%m-%d',close_date) as date, sum(net_return) as returns FROM trades where status = 'CLOSED' group by date")
            df = pd.DataFrame(rs.all(), columns=rs.keys())
            
            df['date'] = pd.to_datetime(df['date'], format="%Y-%m-%d")
            df = df.set_index('date')
            return df
        finally:
            session.close()

    def resetDB(self):
        
        session = self._connect()
        try:
            
            session.execute("delete from trades")
            session.commit()
            #self.seedReturns()

        finally:
            session.close()

    def getOrderByStatus(self, status):
        
        session = self._connect()
        try:
            
            trades = session.execute(f"select *, strftime('%m-%d-%Y', close_date) as date  from trades where status='{status}' order by close_date asc")
            df = pd.DataFrame(trades.all(), columns=trades.keys())
            return df

        finally:
            session.close()

    def seedReturns(self):
        
        date_1 = datetime.now() - relativedelta(months=1)
        
        session = self._connect()
        
        try:
            trade_1 = Trade()
            trade_1.id = 1
            trade_1.close_date = date_1
            trade_1.net_return = 0
            trade_1.avg_open_price = 0
            trade_1.avg_close_price = 0
            trade_1.status = "CLOSED"

            session.add(trade_1)
            session.commit()

        finally:
            session.close()

    def get_trade_by_profit_order_id(self, profit_order_id):
            
            logger.debug(f"get_trade_by_profit_order_id: {profit_order_id}")
            session = self._connect()
            try:
                trade = session.query(Trade).filter_by(profit_order_id=profit_order_id).first()
                return trade
            finally:
                session.close()
    
    def get_trade_by_stop_order_id(self, stop_order_id):

        logger.debug(f"get_trade_by_stop_order_id: {stop_order_id}")
        session = self._connect()
        try:
            trade = session.query(Trade).filter_by(stop_order_id=stop_order_id).first()
            return trade
        finally:
            session.close()
 
    def get_trade_by_order_id(self, order_id):

        trade = self.get_trade_by_profit_order_id(order_id)
        if trade == None:
            trade = self.get_trade_by_stop_order_id(order_id)
        if trade == None:
            session = self._connect()
            try:
                trade = session.query(Trade).get(order_id)
            finally:
                session.close()

        return trade
    
    def get_daily_net_return(self):
        
        session = self._connect()
        try:

            today = datetime.now().date()
            result = session.query(Trade)\
                .filter(Trade.close_date >= today)\
                .filter(Trade.close_date < today + relativedelta(days=1))\
                .filter(Trade.status == "CLOSED")\
                .with_entities(func.sum(Trade.net_return))\
                .scalar()
            
            return float(result) if result is not None else 0.0
            
        except Exception as e:
            logger.error(f"Error getting daily net return: {e}")
            return -1
        finally:
            session.close()
    
    def get_daily_usd_net_return(self):
        """Get daily net return converted to USD"""
        
        session = self._connect()
        try:
            today = datetime.now().date()
            result = session.query(Trade)\
                .filter(Trade.close_date >= today)\
                .filter(Trade.close_date < today + relativedelta(days=1))\
                .filter(Trade.status == "CLOSED")\
                .with_entities(func.sum(Trade.net_profit))\
                .scalar()
            
            return float(result) if result is not None else 0.0
            
        except Exception as e:
            logger.error(f"Error getting daily USD net return: {e}")
            return -1
        finally:
            session.close()