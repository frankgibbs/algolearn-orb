from sqlalchemy import Column, Integer, String, Date, Time, Float, Boolean, DateTime, Text
from sqlalchemy.sql import func
from src import Base

class TradeDecision(Base):
    """Audit trail of all trading decisions for stock ORB strategy"""

    __tablename__ = "trade_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    action = Column(String(10), nullable=False)  # LONG, SHORT, NONE
    reason = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)  # 0-100
    executed = Column(Boolean, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    def __repr__(self):
        status = "EXECUTED" if self.executed else "SKIPPED"
        return f"<TradeDecision(symbol='{self.symbol}', action='{self.action}', " \
               f"confidence={self.confidence:.0f}%, {status})>"