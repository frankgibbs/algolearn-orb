"""
OptionPosition Model - Tracks multi-leg option spreads

Supports vertical spreads, iron condors, butterflies, and other defined-risk strategies.
Each position can have 2-4 legs tracked in the OptionLeg table.
"""

from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, validates
from src import Base
from datetime import datetime


class OptionPosition(Base):
    """Option position tracking for multi-leg spreads"""

    __tablename__ = "option_positions"

    # Core identification
    id = Column(Integer, primary_key=True, autoincrement=False)  # Parent order ID from IB
    symbol = Column(String(10), nullable=False)
    strategy_type = Column(String(50), nullable=False)  # "BULL_PUT_SPREAD", "IRON_CONDOR", etc.

    # Entry details
    entry_date = Column(DateTime, nullable=False)
    expiration_date = Column(DateTime, nullable=False)
    dte_at_entry = Column(Integer, nullable=False)  # Days to expiration at entry

    # Pricing
    net_credit = Column(Float, nullable=False)  # Credit received (positive) or debit paid (negative)
    max_risk = Column(Float, nullable=False)  # Maximum possible loss
    max_profit = Column(Float, nullable=False)  # Maximum possible profit
    roi_target = Column(Float)  # Expected ROI percentage
    entry_iv = Column(Float)  # Implied volatility at entry (ATM)

    # Current status
    status = Column(String(20), nullable=False, default="PENDING")  # "PENDING", "OPEN", "CLOSED", "CANCELLED"
    current_value = Column(Float)  # Current mid price of the spread
    unrealized_pnl = Column(Float, default=0.0)  # Current unrealized profit/loss
    realized_pnl = Column(Float)  # Final profit/loss after close

    # Exit details
    exit_date = Column(DateTime)
    exit_value = Column(Float)  # Closing price of spread
    exit_reason = Column(String(200))  # "PROFIT_TARGET", "STOP_LOSS", "EXPIRATION", "MANUAL"

    # Risk management flags
    profit_target_hit = Column(Boolean, default=False)  # Hit 50-75% profit target
    needs_management = Column(Boolean, default=False)  # Approaching expiration or breakeven

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    legs = relationship("OptionLeg", back_populates="position", cascade="all, delete-orphan")

    @validates('strategy_type')
    def validate_strategy_type(self, key, strategy_type):
        """Validate that strategy type is recognized"""
        valid_strategies = [
            'BULL_PUT_SPREAD',
            'BEAR_CALL_SPREAD',
            'IRON_CONDOR',
            'IRON_BUTTERFLY',
            'LONG_CALL_SPREAD',
            'LONG_PUT_SPREAD',
            'SHORT_STRANGLE',
            'SHORT_STRADDLE',
            'CALENDAR_SPREAD'
        ]
        if strategy_type not in valid_strategies:
            raise ValueError(f"Strategy type must be one of {valid_strategies}, got '{strategy_type}'")
        return strategy_type

    @validates('status')
    def validate_status(self, key, status):
        """Validate that status is valid"""
        valid_statuses = ['PENDING', 'OPEN', 'CLOSED', 'CANCELLED']
        if status not in valid_statuses:
            raise ValueError(f"Status must be one of {valid_statuses}, got '{status}'")
        return status

    @property
    def days_to_expiration(self):
        """Calculate days remaining until expiration"""
        if self.expiration_date:
            delta = self.expiration_date - datetime.now()
            return max(0, delta.days)
        return None

    @property
    def pct_of_max_profit(self):
        """Calculate percentage of maximum profit achieved"""
        if self.max_profit and self.max_profit > 0 and self.unrealized_pnl is not None:
            return (self.unrealized_pnl / self.max_profit) * 100
        return 0.0

    @property
    def actual_roi(self):
        """Calculate actual ROI based on unrealized P&L"""
        if self.max_risk and self.max_risk > 0 and self.unrealized_pnl is not None:
            return (self.unrealized_pnl / self.max_risk) * 100
        return 0.0

    @property
    def is_credit_spread(self):
        """Check if this is a credit strategy (positive net_credit)"""
        return self.net_credit > 0

    @property
    def is_debit_spread(self):
        """Check if this is a debit strategy (negative net_credit)"""
        return self.net_credit < 0

    def __repr__(self):
        return f"<OptionPosition(id={self.id}, symbol='{self.symbol}', " \
               f"strategy='{self.strategy_type}', status='{self.status}', " \
               f"credit=${self.net_credit:.2f}, dte={self.days_to_expiration}, " \
               f"pnl=${self.unrealized_pnl or 0:.2f})>"
