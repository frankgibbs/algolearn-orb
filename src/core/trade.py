from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy import create_engine
from sqlalchemy.sql import func

from src import Base

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    open_date = Column(DateTime, server_default=func.now())
    close_date = Column(DateTime)
    status = Column(String)
    symbol = Column(String)
    quantity = Column(Integer)
    contract_id = Column(Integer)
    avg_open_price = Column(Float)
    avg_close_price = Column(Float)
    net_profit = Column(Float)
    net_return = Column(Float)
    profit_order_id = Column(Integer)
    stop_order_id = Column(Integer)
    direction = Column(Integer)
    open_trade_index = Column(DateTime)
    close_trade_index = Column(DateTime)
    open_trade_marker = Column(Float)
    close_trade_marker = Column(Float)
    stop_price = Column(Float)
    initial_stop_price = Column(Float)  # Original stop price when trade opened
    margin_required = Column(Float)     # Actual margin requirement for this trade
    stop_moved = Column(Integer)
    take_profit_price = Column(Float, nullable=False)    # Target price for trailing activation
    setup_validity_minutes = Column(Integer, nullable=False)  # Trade-specific expiration time
    entry_reasoning = Column(String, nullable=False)     # AI's analysis reasoning
    confidence_score = Column(Integer, nullable=False)   # AI confidence score (0-100)
    strategy_name = Column(String, nullable=False)       # Strategy that generated this trade
    
    def to_str(self):
        return self.__repr__
    
    def __repr__(self):
        return str({
            "id": self.id,
            "symbol": self.symbol,
            "status": self.status,
            "open_date": self.open_date,
            "close_date": self.close_date,
            "avg_open_price": self.avg_open_price,
            "avg_close_price": self.avg_close_price,
            "net_profit": self.net_profit,
            "net_return": self.net_return,
            "quantity": self.quantity,
            "profit_order_id": self.profit_order_id,
            "stop_order_id": self.stop_order_id,
            "direction": self.direction,
            "open_trade_index": self.open_trade_index,
            "close_trade_index": self.close_trade_index,
            "open_trade_marker": self.open_trade_marker,
            "close_trade_marker": self.close_trade_marker,
            "stop_price": self.stop_price,
            "initial_stop_price": self.initial_stop_price,
            "margin_required": self.margin_required,
            "stop_moved": self.stop_moved,
            "take_profit_price": self.take_profit_price,
            "setup_validity_minutes": self.setup_validity_minutes,
            "entry_reasoning": self.entry_reasoning,
            "confidence_score": self.confidence_score,
            "strategy_name": self.strategy_name
        })