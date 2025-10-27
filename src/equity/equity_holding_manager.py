"""
EquityHoldingManager - Database operations for PowerOptions equity holdings

Handles CRUD operations for EquityHolding model.
Follows same pattern as OptionDatabaseManager for consistency.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src import logger, Base
from datetime import datetime
from typing import List, Optional

from src.equity.models.equity_holding import EquityHolding


class EquityHoldingManager:
    """Database manager for equity holdings - uses SQLAlchemy declarative models"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.application_context = application_context
        self.client = application_context.client

        # Use same database as stocks/options
        db_file_name = "sqlite:///data/stocks.db"
        self.engine = create_engine(db_file_name)

        # Create tables if they don't exist
        Base.metadata.create_all(bind=self.engine)

        logger.info("EquityHoldingManager initialized - tables created from models")

    def get_session(self):
        """Get a database session"""
        Session = sessionmaker(bind=self.engine)
        return Session()

    # ==================== EquityHolding CRUD ====================

    def create_holding(
        self,
        purchase_order_id: int,
        symbol: str,
        total_shares: int,
        original_cost_basis: float,
        initial_purchase_date: datetime
    ) -> EquityHolding:
        """
        Create a new equity holding in PENDING status

        NOTE: Premium tracking removed from model - use EquityService.calculate_effective_cost_basis()
        for real-time cost basis calculation from linked option positions.

        Args:
            purchase_order_id: IB order ID for stock purchase (required)
            symbol: Stock symbol (required)
            total_shares: Number of shares purchased (required)
            original_cost_basis: Cost per share when purchased (required)
            initial_purchase_date: Date of initial purchase (required)

        Returns:
            EquityHolding object

        Raises:
            ValueError: If any required parameter is missing or invalid
            RuntimeError: If holding creation fails
        """
        # Validation
        if purchase_order_id is None:
            raise ValueError("purchase_order_id is REQUIRED")
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if total_shares is None or total_shares <= 0:
            raise ValueError("total_shares is REQUIRED and must be positive")
        if original_cost_basis is None or original_cost_basis <= 0:
            raise ValueError("original_cost_basis is REQUIRED and must be positive")
        if initial_purchase_date is None:
            raise ValueError("initial_purchase_date is REQUIRED")

        session = self.get_session()
        try:
            # Check if holding already exists for this symbol
            existing = session.query(EquityHolding).filter_by(symbol=symbol).first()
            if existing:
                raise ValueError(f"Equity holding for {symbol} already exists (id={existing.id})")

            holding = EquityHolding(
                purchase_order_id=purchase_order_id,
                symbol=symbol,
                total_shares=total_shares,
                original_cost_basis=original_cost_basis,
                initial_purchase_date=initial_purchase_date,
                status='PENDING'  # Start as pending until order fills
            )

            session.add(holding)
            session.commit()

            logger.info(f"Equity holding created: {holding}")
            return holding

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create equity holding: {e}")
            raise RuntimeError(f"Equity holding creation failed: {e}")
        finally:
            session.close()

    def get_pending_holdings(self) -> List[EquityHolding]:
        """
        Get all PENDING equity holdings (orders not filled yet)

        Returns:
            List of EquityHolding objects with status='PENDING'
        """
        session = self.get_session()
        try:
            holdings = session.query(EquityHolding).filter_by(status='PENDING').all()
            logger.debug(f"Found {len(holdings)} pending equity holdings")
            return holdings
        finally:
            session.close()

    def get_open_holdings(self) -> List[EquityHolding]:
        """
        Get all OPEN equity holdings (available for covered calls/ratio spreads)

        Returns:
            List of EquityHolding objects with status='OPEN'
        """
        session = self.get_session()
        try:
            holdings = session.query(EquityHolding).filter_by(status='OPEN').all()
            logger.debug(f"Found {len(holdings)} open equity holdings")
            return holdings
        finally:
            session.close()

    def get_holding_by_id(self, holding_id: int) -> Optional[EquityHolding]:
        """
        Get equity holding by ID

        Args:
            holding_id: Equity holding ID (required)

        Returns:
            EquityHolding object or None if not found

        Raises:
            ValueError: If holding_id is None
        """
        if holding_id is None:
            raise ValueError("holding_id is REQUIRED")

        session = self.get_session()
        try:
            holding = session.query(EquityHolding).filter_by(id=holding_id).first()
            return holding
        finally:
            session.close()

    def get_holding_by_symbol(self, symbol: str) -> Optional[EquityHolding]:
        """
        Get equity holding by symbol

        Args:
            symbol: Stock symbol (required)

        Returns:
            EquityHolding object or None if not found

        Raises:
            ValueError: If symbol is None or empty
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        session = self.get_session()
        try:
            holding = session.query(EquityHolding).filter_by(symbol=symbol).first()
            return holding
        finally:
            session.close()

    def update_holding_status(
        self,
        holding_id: int,
        status: str,
        **kwargs
    ) -> EquityHolding:
        """
        Update equity holding status and optional fields

        Args:
            holding_id: Equity holding ID (required)
            status: New status (required) - "PENDING", "OPEN", "CLOSED"
            **kwargs: Optional fields to update (e.g., entry_price, fill_time)

        Returns:
            Updated EquityHolding object

        Raises:
            ValueError: If holding_id or status is None
            RuntimeError: If holding not found or update fails
        """
        if holding_id is None:
            raise ValueError("holding_id is REQUIRED")
        if not status:
            raise ValueError("status is REQUIRED")

        session = self.get_session()
        try:
            holding = session.query(EquityHolding).filter_by(id=holding_id).first()

            if not holding:
                raise RuntimeError(f"Equity holding {holding_id} not found")

            # Update status
            holding.status = status

            # Update optional fields
            for key, value in kwargs.items():
                if hasattr(holding, key):
                    setattr(holding, key, value)

            session.commit()

            logger.info(f"Equity holding {holding_id} status updated to {status}")
            return holding

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update equity holding status: {e}")
            raise RuntimeError(f"Equity holding status update failed: {e}")
        finally:
            session.close()

    # NOTE: update_premium() removed - premium is now calculated on-demand
    # via EquityService.calculate_effective_cost_basis() using real-time IB data

    def close_holding(
        self,
        holding_id: int,
        exit_price: float,
        exit_reason: str,
        realized_pnl: float
    ) -> EquityHolding:
        """
        Close equity holding (assignment or manual close)

        Args:
            holding_id: Equity holding ID (required)
            exit_price: Exit price per share (required)
            exit_reason: Reason for exit (required) - "ASSIGNED", "MANUAL_CLOSE"
            realized_pnl: Realized profit/loss on stock only (required)

        Returns:
            Closed EquityHolding object

        Raises:
            ValueError: If any parameter is None or invalid
            RuntimeError: If holding not found or close fails
        """
        if holding_id is None:
            raise ValueError("holding_id is REQUIRED")
        if exit_price is None or exit_price <= 0:
            raise ValueError("exit_price is REQUIRED and must be positive")
        if not exit_reason:
            raise ValueError("exit_reason is REQUIRED")
        if realized_pnl is None:
            raise ValueError("realized_pnl is REQUIRED")

        session = self.get_session()
        try:
            holding = session.query(EquityHolding).filter_by(id=holding_id).first()

            if not holding:
                raise RuntimeError(f"Equity holding {holding_id} not found")

            # Update to CLOSED status
            holding.status = 'CLOSED'
            holding.exit_date = datetime.now()
            holding.exit_price = exit_price
            holding.exit_reason = exit_reason
            holding.realized_pnl = realized_pnl

            session.commit()

            logger.info(
                f"Equity holding {holding_id} ({holding.symbol}) closed: "
                f"exit_price=${exit_price:.2f}, realized_pnl=${realized_pnl:.2f}, "
                f"reason={exit_reason}"
            )
            return holding

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to close equity holding: {e}")
            raise RuntimeError(f"Equity holding close failed: {e}")
        finally:
            session.close()

    def update_shares(
        self,
        holding_id: int,
        new_total_shares: int
    ) -> EquityHolding:
        """
        Update total shares (after assignment or additional purchase)

        Args:
            holding_id: Equity holding ID (required)
            new_total_shares: New total share count (required)

        Returns:
            Updated EquityHolding object

        Raises:
            ValueError: If any parameter is None or invalid
            RuntimeError: If holding not found or update fails
        """
        if holding_id is None:
            raise ValueError("holding_id is REQUIRED")
        if new_total_shares is None or new_total_shares < 0:
            raise ValueError("new_total_shares is REQUIRED and must be >= 0")

        session = self.get_session()
        try:
            holding = session.query(EquityHolding).filter_by(id=holding_id).first()

            if not holding:
                raise RuntimeError(f"Equity holding {holding_id} not found")

            old_shares = holding.total_shares
            holding.total_shares = new_total_shares

            session.commit()

            logger.info(
                f"Equity holding {holding_id} ({holding.symbol}) shares updated: "
                f"{old_shares} → {new_total_shares}"
            )
            return holding

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update equity holding shares: {e}")
            raise RuntimeError(f"Equity holding shares update failed: {e}")
        finally:
            session.close()
