"""add_unique_constraint_opening_range_symbol_date

Revision ID: 7g9j0683ii27
Revises: 6f8i9572hh16
Create Date: 2025-11-07 19:00:00.000000

Database Integrity Enhancement:
- Add unique constraint on (symbol, date) to prevent duplicate opening ranges
- Ensures only one opening range per symbol per trading day
- Prevents race conditions if system restarts during calculation

This complements the existing application-level duplicate check with
database-level enforcement for true data integrity.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7g9j0683ii27'
down_revision: Union[str, None] = '6f8i9572hh16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add unique constraint on (symbol, date) using batch mode for SQLite compatibility
    with op.batch_alter_table('opening_ranges', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uix_opening_range_symbol_date',
            ['symbol', 'date']
        )


def downgrade() -> None:
    # Drop unique constraint using batch mode for SQLite compatibility
    with op.batch_alter_table('opening_ranges', schema=None) as batch_op:
        batch_op.drop_constraint(
            'uix_opening_range_symbol_date',
            type_='unique'
        )
