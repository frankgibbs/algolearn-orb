"""
StockMargin Model - Persistent storage of margin requirements

Stores margin per share for position sizing calculations.
Updated on-demand when opening ranges are calculated for symbols.
"""

from sqlalchemy import Column, String, Float, Boolean, DateTime
from sqlalchemy.sql import func
from src import Base


class StockMargin(Base):
    """Stock margin requirements for position sizing"""

    __tablename__ = "stock_margins"

    # Primary key
    symbol = Column(String(10), primary_key=True)

    # Margin data
    margin_per_share = Column(Float, nullable=False)  # Margin required per share
    synthetic = Column(Boolean, default=False)  # True if calculated from average, False if real IB margin

    # Timestamps
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<StockMargin(symbol='{self.symbol}', " \
               f"margin=${self.margin_per_share:.2f}, " \
               f"synthetic={self.synthetic})>"
