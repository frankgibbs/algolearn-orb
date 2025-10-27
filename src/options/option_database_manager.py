"""
OptionDatabaseManager - Database operations for multi-leg option positions

Handles CRUD operations for OptionPosition and OptionLeg models.
Follows same pattern as StocksDatabaseManager for consistency.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, joinedload
from src import logger, Base
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

from src.options.models.option_position import OptionPosition
from src.options.models.option_leg import OptionLeg


class OptionDatabaseManager:
    """Database manager for options trading - uses SQLAlchemy declarative models"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.application_context = application_context
        self.client = application_context.client

        # Use same database as stocks for now (could be separate)
        db_file_name = "sqlite:///data/stocks.db"
        self.engine = create_engine(db_file_name)

        # Create tables if they don't exist
        Base.metadata.create_all(bind=self.engine)

        logger.info("OptionDatabaseManager initialized - tables created from models")

    def get_session(self):
        """Get a database session"""
        Session = sessionmaker(bind=self.engine)
        return Session()

    # ==================== OptionPosition CRUD ====================

    def save_position(
        self,
        order_id: int,
        symbol: str,
        strategy_type: str,
        entry_date: datetime,
        expiration_date: datetime,
        dte_at_entry: int,
        net_credit: float,
        max_risk: float,
        max_profit: float,
        roi_target: float,
        entry_iv: float,
        legs: List[Dict],
        equity_holding_id: int = None
    ) -> OptionPosition:
        """
        Save a new option position with its legs to database

        Args:
            order_id: IB parent order ID (required)
            symbol: Stock symbol (required)
            strategy_type: Strategy name like "BULL_PUT_SPREAD" (required)
            entry_date: Entry datetime (required)
            expiration_date: Option expiration datetime (required)
            dte_at_entry: Days to expiration at entry (required)
            net_credit: Net credit received (positive) or debit paid (negative) (required)
            max_risk: Maximum possible loss (required)
            max_profit: Maximum possible profit (required)
            roi_target: Expected ROI percentage (required)
            entry_iv: Implied volatility at entry (required)
            legs: List of leg dicts with keys: action, strike, right, expiry, quantity (required)
            equity_holding_id: Link to equity holding for covered calls/ratio spreads (optional)

        Returns:
            OptionPosition object

        Raises:
            ValueError: If any required parameter is missing or invalid
        """
        if not order_id:
            raise ValueError("order_id is REQUIRED")
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if not strategy_type:
            raise ValueError("strategy_type is REQUIRED")
        if not entry_date:
            raise ValueError("entry_date is REQUIRED")
        if not expiration_date:
            raise ValueError("expiration_date is REQUIRED")
        if dte_at_entry is None or dte_at_entry < 0:
            raise ValueError("dte_at_entry is REQUIRED and must be >= 0")
        if net_credit is None:
            raise ValueError("net_credit is REQUIRED")
        if max_risk is None or max_risk <= 0:
            raise ValueError("max_risk is REQUIRED and must be > 0")
        if max_profit is None or max_profit <= 0:
            raise ValueError("max_profit is REQUIRED and must be > 0")
        if not legs or len(legs) < 1:
            raise ValueError("legs is REQUIRED and must have at least 1 leg")

        session = self.get_session()
        try:
            # Check if position already exists
            existing = session.query(OptionPosition).filter_by(id=order_id).first()
            if existing:
                logger.warning(f"Option position already exists for order_id {order_id}")
                return existing

            # Create position
            position = OptionPosition(
                id=order_id,
                symbol=symbol,
                strategy_type=strategy_type,
                entry_date=entry_date,
                expiration_date=expiration_date,
                dte_at_entry=dte_at_entry,
                net_credit=net_credit,
                max_risk=max_risk,
                max_profit=max_profit,
                roi_target=roi_target,
                entry_iv=entry_iv,
                equity_holding_id=equity_holding_id,
                status="PENDING"
            )

            # Create legs
            for leg_data in legs:
                leg = OptionLeg(
                    position_id=order_id,
                    action=leg_data['action'],
                    strike=leg_data['strike'],
                    right=leg_data['right'],
                    expiry=leg_data['expiry'],
                    quantity=leg_data.get('quantity', 1)
                )
                position.legs.append(leg)

            session.add(position)
            session.commit()
            session.refresh(position)  # Get updated object with relationships

            logger.info(f"Option position saved: {order_id} {symbol} {strategy_type}")
            return position

        except Exception as e:
            session.rollback()
            logger.error(f"Error saving option position: {e}")
            raise
        finally:
            session.close()

    def update_position_status(self, order_id: int, status: str, entry_price: float = None):
        """
        Update position status (PENDING -> OPEN -> CLOSED)

        Args:
            order_id: Position ID (required)
            status: New status (required)
            entry_price: Average entry price if filled (optional)

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If position not found
        """
        if not order_id:
            raise ValueError("order_id is REQUIRED")
        if not status:
            raise ValueError("status is REQUIRED")

        session = self.get_session()
        try:
            position = session.query(OptionPosition).filter_by(id=order_id).first()
            if not position:
                raise RuntimeError(f"Option position not found for order_id {order_id}")

            position.status = status
            if entry_price is not None and status == "OPEN":
                position.current_value = entry_price

            session.commit()
            logger.info(f"Position {order_id} status updated to {status}")

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating position status: {e}")
            raise
        finally:
            session.close()

    # NOTE: update_position_pnl() removed - unrealized P&L calculated on-demand
    # Use get_option_quote MCP tool to fetch real-time prices when needed

    def set_closing_order(self, opening_order_id: int, closing_order_id: int, exit_reason: str):
        """
        Link a closing order to its opening position

        Args:
            opening_order_id: Original position ID (required)
            closing_order_id: Closing order ID from IB (required)
            exit_reason: Reason for closing (required)

        Raises:
            ValueError: If parameters invalid
            RuntimeError: If position not found or not OPEN
        """
        if not opening_order_id:
            raise ValueError("opening_order_id is REQUIRED")
        if not closing_order_id:
            raise ValueError("closing_order_id is REQUIRED")
        if not exit_reason:
            raise ValueError("exit_reason is REQUIRED")

        session = self.get_session()
        try:
            position = session.query(OptionPosition).filter_by(id=opening_order_id).first()
            if not position:
                raise RuntimeError(f"Position not found: {opening_order_id}")
            if position.status != "OPEN":
                raise RuntimeError(f"Position {opening_order_id} is not OPEN (status: {position.status})")
            if position.closing_order_id != 0:
                raise RuntimeError(f"Position {opening_order_id} already has closing order: {position.closing_order_id}")

            position.closing_order_id = closing_order_id
            position.exit_reason = exit_reason
            session.commit()

            logger.info(f"Position {opening_order_id} linked to closing order {closing_order_id}")

        except Exception as e:
            session.rollback()
            logger.error(f"Error setting closing order: {e}")
            raise
        finally:
            session.close()

    def close_position(self, order_id: int, exit_value: float, exit_reason: str, realized_pnl: float):
        """
        Close an option position

        Args:
            order_id: Position ID (required)
            exit_value: Closing price of spread (required)
            exit_reason: Reason for close (required)
            realized_pnl: Final realized profit/loss (required)

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If position not found
        """
        if not order_id:
            raise ValueError("order_id is REQUIRED")
        if exit_value is None:
            raise ValueError("exit_value is REQUIRED")
        if not exit_reason:
            raise ValueError("exit_reason is REQUIRED")
        if realized_pnl is None:
            raise ValueError("realized_pnl is REQUIRED")

        session = self.get_session()
        try:
            position = session.query(OptionPosition).filter_by(id=order_id).first()
            if not position:
                raise RuntimeError(f"Option position not found for order_id {order_id}")

            position.status = "CLOSED"
            position.exit_date = datetime.now()
            position.exit_value = exit_value
            position.exit_reason = exit_reason
            position.realized_pnl = realized_pnl

            session.commit()
            logger.info(f"Position {order_id} closed: {exit_reason}, P&L ${realized_pnl:.2f}")

        except Exception as e:
            session.rollback()
            logger.error(f"Error closing position: {e}")
            raise
        finally:
            session.close()

    def get_position(self, order_id: int) -> Optional[OptionPosition]:
        """
        Get a specific option position by order ID

        Args:
            order_id: Position ID (required)

        Returns:
            OptionPosition object or None if not found

        Raises:
            ValueError: If order_id is invalid
        """
        if not order_id:
            raise ValueError("order_id is REQUIRED")

        session = self.get_session()
        try:
            position = session.query(OptionPosition).options(joinedload(OptionPosition.legs)).filter_by(id=order_id).first()
            return position
        finally:
            session.close()

    def get_open_positions(self, symbol: str = None) -> List[OptionPosition]:
        """
        Get all open option positions

        Args:
            symbol: Optional symbol filter

        Returns:
            List of OptionPosition objects
        """
        session = self.get_session()
        try:
            query = session.query(OptionPosition).options(joinedload(OptionPosition.legs)).filter_by(status="OPEN")
            if symbol:
                query = query.filter_by(symbol=symbol)
            positions = query.all()
            return positions
        finally:
            session.close()

    def get_all_positions(self, days_back: int = 30, symbol: str = None) -> List[OptionPosition]:
        """
        Get all option positions within date range

        Args:
            days_back: Number of days back to query (default: 30)
            symbol: Optional symbol filter

        Returns:
            List of OptionPosition objects

        Raises:
            ValueError: If days_back is invalid
        """
        if days_back is None or days_back < 0:
            raise ValueError("days_back must be >= 0")

        session = self.get_session()
        try:
            cutoff_date = datetime.now() - timedelta(days=days_back)
            query = session.query(OptionPosition).options(joinedload(OptionPosition.legs)).filter(OptionPosition.entry_date >= cutoff_date)

            if symbol:
                query = query.filter_by(symbol=symbol)

            positions = query.order_by(OptionPosition.entry_date.desc()).all()
            return positions
        finally:
            session.close()

    # ==================== OptionLeg Operations ====================

    def update_leg_fill(self, leg_id: int, fill_price: float, fill_time: str, commission: float = 0.0):
        """
        Update leg with fill details

        Args:
            leg_id: Leg ID (required)
            fill_price: Fill price per contract (required)
            fill_time: Timestamp of fill (required)
            commission: Commission for this leg (default: 0.0)

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If leg not found
        """
        if not leg_id:
            raise ValueError("leg_id is REQUIRED")
        if fill_price is None:
            raise ValueError("fill_price is REQUIRED")
        if not fill_time:
            raise ValueError("fill_time is REQUIRED")

        session = self.get_session()
        try:
            leg = session.query(OptionLeg).filter_by(id=leg_id).first()
            if not leg:
                raise RuntimeError(f"Option leg not found for id {leg_id}")

            leg.fill_price = fill_price
            leg.fill_time = fill_time
            leg.commission = commission

            session.commit()
            logger.debug(f"Leg {leg_id} fill updated: ${fill_price:.2f}")

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating leg fill: {e}")
            raise
        finally:
            session.close()
