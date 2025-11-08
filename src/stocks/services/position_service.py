"""
Position Management Service

Provides shared utilities for position calculations and management.
"""
from src.core.application_context import ApplicationContext


class PositionService:
    """Service for position-related calculations and utilities"""

    def __init__(self, application_context: ApplicationContext):
        """
        Initialize position service

        Args:
            application_context: Application context (required)

        Raises:
            ValueError: If application_context is None
        """
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.application_context = application_context
        self.state_manager = application_context.state_manager
        self.client = application_context.client
        self.database_manager = application_context.database_manager

    def calculate_pnl(self, position, exit_price):
        """
        Calculate P&L for a position at a given exit price

        Handles both LONG and SHORT positions correctly:
        - LONG: profit when exit_price > entry_price
        - SHORT: profit when exit_price < entry_price

        Args:
            position: Position record with direction, entry_price, and shares (required)
            exit_price: Exit price for P&L calculation (required)

        Returns:
            P&L as float (positive = profit, negative = loss)

        Raises:
            ValueError: If any parameter is None or invalid

        Examples:
            >>> # LONG position: bought at $100, selling at $105
            >>> pnl = service.calculate_pnl(long_position, 105.0)
            >>> # Returns: +500.0 (for 100 shares)

            >>> # SHORT position: sold at $100, buying back at $95
            >>> pnl = service.calculate_pnl(short_position, 95.0)
            >>> # Returns: +500.0 (for 100 shares)
        """
        if position is None:
            raise ValueError("position is REQUIRED")
        if exit_price is None:
            raise ValueError("exit_price is REQUIRED")
        if exit_price <= 0:
            raise ValueError(f"exit_price must be positive, got: {exit_price}")

        if position.direction == 'LONG':
            # LONG: profit = (exit_price - entry_price) × shares
            return (exit_price - position.entry_price) * position.shares
        elif position.direction == 'SHORT':
            # SHORT: profit = (entry_price - exit_price) × shares
            return (position.entry_price - exit_price) * position.shares
        else:
            raise ValueError(f"Invalid position direction: {position.direction}")
