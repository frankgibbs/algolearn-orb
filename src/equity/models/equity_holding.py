"""
EquityHolding Model - Tracks long-term stock holdings for PowerOptions strategy

Stores cost basis and premium tracking for equity positions with covered calls/ratio spreads.
Links to OptionPosition records for complete portfolio view.
"""

from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, validates
from src import Base


class EquityHolding(Base):
    """Equity holding tracking for PowerOptions covered call strategy"""

    __tablename__ = "equity_holdings"

    # Core identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_order_id = Column(Integer, nullable=False)  # IB order ID for stock purchase
    symbol = Column(String(10), nullable=False, unique=True)

    # Position details
    total_shares = Column(Integer, nullable=False)
    original_cost_basis = Column(Float, nullable=False)  # Cost per share when purchased
    initial_purchase_date = Column(DateTime, nullable=False)

    # NOTE: Premium tracking removed - calculated on-demand via EquityService
    # using real-time data from linked option_positions

    # Status tracking (consistent with other position types)
    status = Column(String(20), nullable=False)  # "PENDING", "OPEN", "CLOSED"

    # Exit details (if assigned or manually closed)
    exit_date = Column(DateTime)
    exit_price = Column(Float)  # Price per share at exit
    exit_reason = Column(String(100))  # "ASSIGNED", "MANUAL_CLOSE"
    realized_pnl = Column(Float)  # Stock P&L only (not including option premium)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationship: one equity holding → many option positions
    option_positions = relationship("OptionPosition", back_populates="equity_holding")

    @validates('status')
    def validate_status(self, key, status):
        """Validate that status follows standard pattern"""
        valid_statuses = ['PENDING', 'OPEN', 'CLOSED']
        if status not in valid_statuses:
            raise ValueError(f"Status must be one of {valid_statuses}, got '{status}'")
        return status

    # NOTE: effective_cost_basis and total_premium_net removed
    # Use EquityService.calculate_effective_cost_basis() for real-time calculation
    # with live IB data for open option positions

    @property
    def is_pending(self):
        """Check if equity purchase is pending (order not filled yet)"""
        return self.status == 'PENDING'

    @property
    def is_open(self):
        """Check if equity holding is active"""
        return self.status == 'OPEN'

    @property
    def is_closed(self):
        """Check if equity holding is closed"""
        return self.status == 'CLOSED'

    def __repr__(self):
        return f"<EquityHolding(id={self.id}, symbol='{self.symbol}', " \
               f"shares={self.total_shares}, status='{self.status}', " \
               f"original_basis=${self.original_cost_basis:.2f})>"
