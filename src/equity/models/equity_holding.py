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

    # Premium tracking (for basis reduction)
    # NOTE: These are required fields with NO defaults - must be explicitly initialized
    premium_collected = Column(Float, nullable=False)  # Total option premium collected
    premium_paid = Column(Float, nullable=False)  # Total option premium paid (buying back)

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

    @property
    def effective_cost_basis(self):
        """
        Calculate effective cost basis per share after premium collected/paid.

        This is the PowerOptions "basis reduction" - option premium lowers your cost basis.

        Returns:
            Float: Effective cost per share after accounting for option premium
        """
        if self.total_shares == 0:
            return 0.0

        net_premium = self.premium_collected - self.premium_paid
        total_stock_cost = self.original_cost_basis * self.total_shares
        effective_total = total_stock_cost - net_premium

        return effective_total / self.total_shares

    @property
    def total_premium_net(self):
        """
        Calculate net premium collected (positive) or paid (negative)

        Returns:
            Float: Net premium (collected - paid)
        """
        return self.premium_collected - self.premium_paid

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
               f"original_basis=${self.original_cost_basis:.2f}, " \
               f"effective_basis=${self.effective_cost_basis:.2f}, " \
               f"net_premium=${self.total_premium_net:.2f})>"
