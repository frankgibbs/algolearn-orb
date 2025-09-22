from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src import Base

class Position(Base):
    """Position tracking for stock ORB trades"""

    __tablename__ = "positions"

    # Core identification
    id = Column(Integer, primary_key=True, autoincrement=False)  # THIS IS the parent order ID!
    stop_order_id = Column(Integer, nullable=False)  # Child stop order
    opening_range_id = Column(Integer, ForeignKey('opening_ranges.id'), nullable=False)

    # Trade details
    symbol = Column(String(10), nullable=False)
    direction = Column(String(10), nullable=False)  # 'LONG' or 'SHORT'
    entry_time = Column(DateTime)
    entry_price = Column(Float)
    shares = Column(Integer, nullable=False)

    # Risk management
    stop_loss_price = Column(Float, nullable=False)  # Original stop price
    take_profit_price = Column(Float, nullable=False)  # Monitored level, NOT an order
    stop_moved = Column(Boolean, default=False)  # True if stop has been modified
    trailing_stop_price = Column(Float)  # Current stop price (if moved)
    range_size = Column(Float, nullable=False)  # For trailing calculations

    # Status tracking
    current_price = Column(Float)
    unrealized_pnl = Column(Float)
    status = Column(String(20), nullable=False)  # 'PENDING', 'OPEN', 'CLOSED'

    # Exit details
    exit_time = Column(DateTime)
    exit_price = Column(Float)
    exit_reason = Column(String(100))
    realized_pnl = Column(Float)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationship to opening range
    opening_range = relationship("OpeningRange", back_populates="positions")

    @property
    def current_stop_price(self):
        """Get the current effective stop price"""
        return self.trailing_stop_price if self.stop_moved else self.stop_loss_price

    @property
    def is_long(self):
        """Check if this is a long position"""
        return self.direction == 'LONG'

    @property
    def is_short(self):
        """Check if this is a short position"""
        return self.direction == 'SHORT'

    def __repr__(self):
        return f"<Position(id={self.id}, symbol='{self.symbol}', " \
               f"direction='{self.direction}', status='{self.status}', " \
               f"entry=${self.entry_price}, stop=${self.current_stop_price}, " \
               f"tp=${self.take_profit_price})>"