from sqlalchemy import Column, Integer, String, Date, Float, DateTime, BigInteger, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src import Base

class OpeningRange(Base):
    """
    Opening range data for stock ORB strategy

    Enhanced for Academic ORB Strategy (Zarattini, Barbon, Aziz 2024):
    - directional_bias: Opening momentum direction (BULLISH/BEARISH)
    - volume: Total volume during opening range period for relative volume calculation
    """

    __tablename__ = "opening_ranges"
    __table_args__ = (
        UniqueConstraint('symbol', 'date', name='uix_opening_range_symbol_date'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    timeframe_minutes = Column(Integer, nullable=False)  # 5, 15, 30, or 60
    range_high = Column(Float, nullable=False)
    range_low = Column(Float, nullable=False)
    range_size = Column(Float, nullable=False)
    range_size_pct = Column(Float, nullable=False)

    # Academic ORB Strategy fields
    directional_bias = Column(String(10), nullable=True)  # BULLISH or BEARISH
    volume = Column(BigInteger, nullable=True)  # Total volume during opening range

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationship to positions
    positions = relationship("Position", back_populates="opening_range")

    @property
    def range_mid(self):
        """Calculate range midpoint (for stop loss placement)"""
        return (self.range_high + self.range_low) / 2

    def __repr__(self):
        return f"<OpeningRange(symbol='{self.symbol}', date='{self.date}', " \
               f"timeframe={self.timeframe_minutes}m, " \
               f"range=${self.range_low:.2f}-${self.range_high:.2f}, " \
               f"size={self.range_size_pct:.1f}%)>"