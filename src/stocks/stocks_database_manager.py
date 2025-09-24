from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.core.observer import IObserver
from src.core.constants import *
from src import logger
from src import Base
from datetime import datetime, date
from sqlalchemy import func

# Import stock models to register with SQLAlchemy
from src.stocks.models.opening_range import OpeningRange
from src.stocks.models.position import Position
from src.stocks.models.stock_candidate import StockCandidate
from src.stocks.models.trade_decision import TradeDecision
# Import core trade model for stock trades
from src.core.trade import Trade

class StocksDatabaseManager(IObserver):
    """Database manager for stock trading - uses SQLAlchemy declarative models"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.application_context = application_context
        self.subject = application_context.subject
        self.client = application_context.client
        self.state_manager = application_context.state_manager
        self.state_manager.subject.subscribe(self)

        # Create stock-specific database
        db_file_name = "sqlite:///data/stocks.db"
        self.engine = create_engine(db_file_name)

        # SQLAlchemy will create all tables from imported models
        Base.metadata.create_all(bind=self.engine)

        logger.info("StocksDatabaseManager initialized - tables created from models")

    def get_session(self):
        """Get a database session"""
        Session = sessionmaker(bind=self.engine)
        return Session()

    def notify(self, observable, *args):
        """Handle events from observer pattern"""
        # Currently no events to handle for stocks database
        pass

    # Opening Range operations
    def save_opening_range(self, symbol, date, timeframe_minutes, range_high, range_low, range_size, range_size_pct):
        """
        Save opening range to database

        Args:
            symbol: Stock symbol (required)
            date: Date of range (required)
            timeframe_minutes: Timeframe in minutes - 15, 30, or 60 (required)
            range_high: High of opening range (required)
            range_low: Low of opening range (required)
            range_size: Absolute size of range (required)
            range_size_pct: Percentage size of range (required)

        Raises:
            ValueError: If any parameter is None or invalid
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if date is None:
            raise ValueError("date is REQUIRED")
        if timeframe_minutes is None:
            raise ValueError("timeframe_minutes is REQUIRED")
        if timeframe_minutes not in [15, 30, 60]:
            raise ValueError("timeframe_minutes must be 15, 30, or 60")
        if range_high is None:
            raise ValueError("range_high is REQUIRED")
        if range_low is None:
            raise ValueError("range_low is REQUIRED")
        if range_size is None:
            raise ValueError("range_size is REQUIRED")
        if range_size_pct is None:
            raise ValueError("range_size_pct is REQUIRED")

        # Validate range values
        if range_high <= range_low:
            raise ValueError(f"Invalid range: high ({range_high}) must be > low ({range_low})")
        if range_size <= 0:
            raise ValueError(f"Invalid range_size: {range_size}")
        if range_size_pct <= 0:
            raise ValueError(f"Invalid range_size_pct: {range_size_pct}")

        session = self.get_session()
        try:
            # Check if range already exists (unique constraint on symbol, date)
            existing = session.query(OpeningRange).filter_by(symbol=symbol, date=date).first()
            if existing:
                logger.warning(f"Opening range already exists for {symbol} on {date}")
                return

            opening_range = OpeningRange(
                symbol=symbol,
                date=date,
                timeframe_minutes=timeframe_minutes,
                range_high=range_high,
                range_low=range_low,
                range_size=range_size,
                range_size_pct=range_size_pct
            )

            session.add(opening_range)
            session.commit()

            logger.info(f"Opening range saved for {symbol}: ${range_low:.2f}-${range_high:.2f} ({range_size_pct:.1f}%)")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save opening range: {e}")
            raise
        finally:
            session.close()

    def get_opening_range(self, symbol, date):
        """
        Get opening range from database

        Args:
            symbol: Stock symbol (required)
            date: Date to query (required)

        Returns:
            OpeningRange object or None if not found

        Raises:
            ValueError: If symbol or date is None
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if date is None:
            raise ValueError("date is REQUIRED")

        session = self.get_session()
        try:
            return session.query(OpeningRange).filter_by(symbol=symbol, date=date).first()
        finally:
            session.close()

    def get_opening_ranges_by_date(self, date):
        """
        Get all opening ranges for a specific date

        Args:
            date: Date to query (required)

        Returns:
            List of OpeningRange objects

        Raises:
            ValueError: If date is None
        """
        if date is None:
            raise ValueError("date is REQUIRED")

        session = self.get_session()
        try:
            return session.query(OpeningRange).filter_by(date=date).all()
        finally:
            session.close()

    # Stock Candidate operations
    def save_candidates(self, candidates_data, scan_date):
        """
        Save stock candidates to database

        Args:
            candidates_data: List of candidate dictionaries (required)
            scan_date: Date of scan (required)

        Raises:
            ValueError: If candidates_data or scan_date is None
        """
        if candidates_data is None:
            raise ValueError("candidates_data is REQUIRED")
        if scan_date is None:
            raise ValueError("scan_date is REQUIRED")

        session = self.get_session()
        try:
            for i, candidate_data in enumerate(candidates_data):
                candidate = StockCandidate(
                    symbol=candidate_data.get('symbol', f'PLACEHOLDER_{i}'),
                    date=scan_date,
                    scan_time=candidate_data.get('scan_time', datetime.now().time()),
                    pre_market_change=candidate_data.get('pre_market_change', 0.0),
                    volume=candidate_data.get('volume', 0),
                    relative_volume=candidate_data.get('relative_volume', 1.0),
                    rank=i + 1,
                    criteria_met=candidate_data.get('criteria_met', 'placeholder'),
                    selected=i < 25  # Select top 25
                )
                session.add(candidate)

            session.commit()
            logger.info(f"Saved {len(candidates_data)} candidates to database")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save candidates: {e}")
            raise
        finally:
            session.close()

    def get_candidates(self, date, selected_only=True):
        """
        Get stock candidates from database

        Args:
            date: Date to query (required)
            selected_only: If True, only return selected candidates

        Returns:
            List of StockCandidate objects

        Raises:
            ValueError: If date is None
        """
        if date is None:
            raise ValueError("date is REQUIRED")

        session = self.get_session()
        try:
            query = session.query(StockCandidate).filter_by(date=date)
            if selected_only:
                query = query.filter_by(selected=True)
            return query.order_by(StockCandidate.rank).all()
        finally:
            session.close()

    # Trade Decision operations
    def save_trade_decision(self, symbol, action, reason, confidence, executed):
        """
        Save trade decision to database for audit trail

        Args:
            symbol: Stock symbol (required)
            action: Trade action - LONG, SHORT, or NONE (required)
            reason: Reasoning for decision (required)
            confidence: Confidence score 0-100 (required)
            executed: Whether trade was executed (required)

        Raises:
            ValueError: If any parameter is None or invalid
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")
        if not action:
            raise ValueError("action is REQUIRED")
        if not reason:
            raise ValueError("reason is REQUIRED")
        if confidence is None:
            raise ValueError("confidence is REQUIRED")
        if executed is None:
            raise ValueError("executed is REQUIRED")

        session = self.get_session()
        try:
            trade_decision = TradeDecision(
                symbol=symbol,
                date=datetime.now().date(),
                time=datetime.now().time(),
                action=action,
                reason=reason,
                confidence=confidence,
                executed=executed
            )

            session.add(trade_decision)
            session.commit()

            logger.info(f"Trade decision saved: {action} {symbol} (confidence: {confidence}%, executed: {executed})")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save trade decision: {e}")
            raise
        finally:
            session.close()

    # Stock Trade operations (using existing Trade model)
    def get_open_stock_positions(self):
        """
        Get all open stock positions

        Returns:
            List of Trade objects with strategy_name containing 'stock' or 'ORB'
        """
        session = self.get_session()
        try:
            return session.query(Trade).filter(
                Trade.status == "OPEN",
                Trade.strategy_name.in_(["ORB", "stock"])
            ).all()
        finally:
            session.close()

    def get_daily_stock_return(self, date=None):
        """
        Get daily return for stock trades only

        Args:
            date: Date to query (defaults to today)

        Returns:
            Float: Daily return for stock trades
        """
        if date is None:
            date = datetime.now().date()

        session = self.get_session()
        try:
            result = session.query(Trade)\
                .filter(Trade.close_date >= date)\
                .filter(Trade.close_date < date)\
                .filter(Trade.status == "CLOSED")\
                .filter(Trade.strategy_name.in_(["ORB", "stock"]))\
                .with_entities(func.sum(Trade.net_return))\
                .scalar()

            return float(result) if result is not None else 0.0

        except Exception as e:
            logger.error(f"Error getting daily stock return: {e}")
            return 0.0
        finally:
            session.close()

    # Position management operations
    def get_max_order_id(self):
        """
        Get maximum order ID from positions table for IBClient order ID calculation

        Returns:
            Integer: Maximum order ID, or 0 if no positions exist
        """
        session = self.get_session()
        try:
            result = session.query(func.max(Position.id)).scalar()
            return int(result) if result is not None else 0
        except Exception as e:
            logger.error(f"Error getting max order ID: {e}")
            return 0
        finally:
            session.close()

    def create_position(self, order_result, opening_range_id, take_profit_price, range_size):
        """
        Create position with explicit ID from order result

        Args:
            order_result: Dict from place_stock_entry_with_stop() (required)
            opening_range_id: ID of the opening range (required)
            take_profit_price: Take profit level to monitor (required)
            range_size: Size of opening range for trailing calculations (required)

        Returns:
            Position: Created position object

        Raises:
            ValueError: If any parameter is invalid
            RuntimeError: If position creation fails
        """
        if not order_result:
            raise ValueError("order_result is REQUIRED")
        if opening_range_id is None:
            raise ValueError("opening_range_id is REQUIRED")
        if take_profit_price is None or take_profit_price <= 0:
            raise ValueError("take_profit_price is REQUIRED and must be positive")
        if range_size is None or range_size <= 0:
            raise ValueError("range_size is REQUIRED and must be positive")

        # Calculate stop loss as midpoint of opening range
        opening_range = self.get_opening_range_by_id(opening_range_id)
        if not opening_range:
            raise ValueError(f"Opening range {opening_range_id} not found")

        stop_loss_price = opening_range.range_mid

        session = self.get_session()
        try:
            position = Position(
                id=order_result['parent_order_id'],  # Explicit ID
                stop_order_id=order_result['stop_order_id'],
                opening_range_id=opening_range_id,
                symbol=order_result['symbol'],
                direction=order_result['action'],  # 'BUY' -> 'LONG', 'SELL' -> 'SHORT'
                shares=order_result['quantity'],
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                range_size=range_size,
                status='PENDING'  # Start as pending until entry fills
            )

            session.add(position)
            session.commit()

            logger.info(f"Position created: {position}")
            return position

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create position: {e}")
            raise RuntimeError(f"Position creation failed: {e}")
        finally:
            session.close()

    def get_opening_range_by_id(self, opening_range_id):
        """
        Get opening range by ID

        Args:
            opening_range_id: ID of opening range

        Returns:
            OpeningRange object or None
        """
        session = self.get_session()
        try:
            return session.query(OpeningRange).filter_by(id=opening_range_id).first()
        finally:
            session.close()

    def get_pending_positions(self):
        """
        Get positions with status='PENDING' for order monitoring

        Returns:
            List of Position objects with PENDING status
        """
        session = self.get_session()
        try:
            return session.query(Position).filter_by(status='PENDING').all()
        finally:
            session.close()

    def get_open_positions(self):
        """
        Get positions with status='OPEN' for management

        Returns:
            List of Position objects with OPEN status
        """
        session = self.get_session()
        try:
            return session.query(Position).filter_by(status='OPEN').all()
        finally:
            session.close()

    def update_position_status(self, position_id, new_status, **kwargs):
        """
        Update position status and other fields

        Args:
            position_id: Position ID to update (required)
            new_status: New status value (required)
            **kwargs: Additional fields to update

        Raises:
            ValueError: If position not found
            RuntimeError: If update fails
        """
        if not position_id:
            raise ValueError("position_id is REQUIRED")
        if not new_status:
            raise ValueError("new_status is REQUIRED")

        session = self.get_session()
        try:
            position = session.query(Position).filter_by(id=position_id).first()
            if not position:
                raise ValueError(f"Position {position_id} not found")

            # Update status
            position.status = new_status

            # Update any additional fields
            for field, value in kwargs.items():
                if hasattr(position, field):
                    setattr(position, field, value)
                else:
                    logger.warning(f"Position does not have field: {field}")

            session.commit()
            logger.info(f"Position {position_id} updated to status: {new_status}")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update position {position_id}: {e}")
            raise RuntimeError(f"Position update failed: {e}")
        finally:
            session.close()

    def get_position_by_id(self, position_id):
        """
        Get position by ID

        Args:
            position_id: Position ID (which is also the parent order ID)

        Returns:
            Position object or None
        """
        session = self.get_session()
        try:
            return session.query(Position).filter_by(id=position_id).first()
        finally:
            session.close()

    def delete_all_positions(self):
        """
        Delete all positions from the database (RESET operation)

        Returns:
            Number of positions deleted

        Raises:
            RuntimeError: If deletion fails
        """
        session = self.get_session()
        try:
            # Count positions before deletion
            count = session.query(Position).count()

            # Delete all positions
            session.query(Position).delete()
            session.commit()

            logger.info(f"Deleted {count} positions from database")
            return count

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to delete positions: {e}")
            raise RuntimeError(f"Failed to delete positions: {e}")
        finally:
            session.close()