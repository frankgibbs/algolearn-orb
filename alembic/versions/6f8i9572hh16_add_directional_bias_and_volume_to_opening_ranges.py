"""add_directional_bias_and_volume_to_opening_ranges

Revision ID: 6f8i9572hh16
Revises: 5e7h8461gg05
Create Date: 2025-11-07 18:30:00.000000

Academic ORB Strategy Enhancement:
- Add directional_bias column (BULLISH/BEARISH) to filter trades by opening momentum
- Add volume column to track opening range volume for relative volume calculations
- Add index on directional_bias for efficient filtering

Based on "A Profitable Day Trading Strategy for The U.S. Equity Market"
(Zarattini, Barbon, Aziz 2024 - Swiss Finance Institute Paper No. 24-98)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f8i9572hh16'
down_revision: Union[str, None] = '5e7h8461gg05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add directional_bias column (BULLISH/BEARISH)
    op.add_column(
        'opening_ranges',
        sa.Column('directional_bias', sa.String(10), nullable=True)
    )

    # Add volume column (total volume during opening range period)
    op.add_column(
        'opening_ranges',
        sa.Column('volume', sa.BigInteger(), nullable=True)
    )

    # Create index on directional_bias for efficient filtering
    op.create_index(
        'idx_opening_ranges_bias',
        'opening_ranges',
        ['directional_bias']
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index('idx_opening_ranges_bias', table_name='opening_ranges')

    # Drop columns
    op.drop_column('opening_ranges', 'volume')
    op.drop_column('opening_ranges', 'directional_bias')
