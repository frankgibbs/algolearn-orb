"""create_stock_margins_table

Revision ID: 5e7h8461gg05
Revises: 4d6g7350ff94
Create Date: 2025-10-24 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e7h8461gg05'
down_revision: Union[str, None] = '4d6g7350ff94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create stock_margins table for persistent margin storage
    # Replaces in-memory cache with database-backed solution
    op.create_table(
        'stock_margins',
        sa.Column('symbol', sa.String(10), nullable=False),
        sa.Column('margin_per_share', sa.Float(), nullable=False),
        sa.Column('synthetic', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('last_updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('symbol')
    )


def downgrade() -> None:
    # Drop stock_margins table
    op.drop_table('stock_margins')
