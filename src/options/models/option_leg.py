"""
OptionLeg Model - Tracks individual legs of multi-leg option spreads

Each leg represents one option contract (buy or sell) as part of a larger strategy.
For example, a Bull Put Spread has 2 legs: sell put (higher strike) + buy put (lower strike).
"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship, validates
from src import Base


class OptionLeg(Base):
    """Individual option leg within a multi-leg position"""

    __tablename__ = "option_legs"

    # Core identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey('option_positions.id', ondelete='CASCADE'), nullable=False)
    order_id = Column(Integer)  # IB order ID for this leg (if filled separately)

    # Option contract details
    action = Column(String(10), nullable=False)  # "BUY" or "SELL"
    strike = Column(Float, nullable=False)
    right = Column(String(1), nullable=False)  # "P" or "C"
    expiry = Column(String(8), nullable=False)  # YYYYMMDD format
    quantity = Column(Integer, nullable=False, default=1)  # Usually 1, but ratio spreads may vary

    # Fill details
    fill_price = Column(Float)  # Actual fill price per contract
    fill_time = Column(String(50))  # Timestamp of fill
    commission = Column(Float, default=0.0)  # Commission for this leg

    # Greeks at entry (optional - for analysis)
    entry_delta = Column(Float)
    entry_gamma = Column(Float)
    entry_theta = Column(Float)
    entry_vega = Column(Float)
    entry_iv = Column(Float)

    # Relationship back to parent position
    position = relationship("OptionPosition", back_populates="legs")

    @validates('action')
    def validate_action(self, key, action):
        """Validate that action is BUY or SELL"""
        if action not in ('BUY', 'SELL'):
            raise ValueError(f"Action must be 'BUY' or 'SELL', got '{action}'")
        return action

    @validates('right')
    def validate_right(self, key, right):
        """Validate that right is P or C"""
        if right not in ('P', 'C'):
            raise ValueError(f"Right must be 'P' or 'C', got '{right}'")
        return right

    @property
    def is_put(self):
        """Check if this is a put option"""
        return self.right == 'P'

    @property
    def is_call(self):
        """Check if this is a call option"""
        return self.right == 'C'

    @property
    def is_long(self):
        """Check if this is a long (buy) position"""
        return self.action == 'BUY'

    @property
    def is_short(self):
        """Check if this is a short (sell) position"""
        return self.action == 'SELL'

    @property
    def notional_value(self):
        """Calculate notional value (price * quantity * multiplier)"""
        if self.fill_price:
            return self.fill_price * self.quantity * 100  # Options multiplier is 100
        return None

    def __repr__(self):
        action_sign = "-" if self.action == "SELL" else "+"
        return f"<OptionLeg({action_sign}{self.quantity} {self.strike}{self.right} @ ${self.fill_price or 0:.2f})>"
