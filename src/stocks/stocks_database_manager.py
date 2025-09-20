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
    def save_opening_range(self, symbol, date, range_high, range_low, range_size, range_size_pct):
        """
        Save opening range to database

        Args:
            symbol: Stock symbol (required)
            date: Date of range (required)
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