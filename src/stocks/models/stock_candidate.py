from sqlalchemy import Column, Integer, String, Date, Time, Float, Boolean, DateTime, Text
from sqlalchemy.sql import func
from src import Base

class StockCandidate(Base):
    """Stock candidate from pre-market scan"""

    __tablename__ = "stock_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    scan_time = Column(Time, nullable=False)
    pre_market_change = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)
    relative_volume = Column(Float, nullable=False)
    rank = Column(Integer, nullable=False)
    criteria_met = Column(Text, nullable=False)
    selected = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<StockCandidate(symbol='{self.symbol}', rank={self.rank}, " \
               f"change={self.pre_market_change:.1f}%, vol={self.relative_volume:.1f}x)>"