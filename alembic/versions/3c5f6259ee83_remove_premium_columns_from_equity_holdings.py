"""remove_premium_columns_from_equity_holdings

Revision ID: 3c5f6259ee83
Revises: 2b3e4148dd72
Create Date: 2025-10-24 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c5f6259ee83'
down_revision: Union[str, None] = '2b3e4148dd72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop premium_collected and premium_paid columns from equity_holdings table
    # Premium is now calculated on-demand via EquityService using real-time IB data
    with op.batch_alter_table('equity_holdings', schema=None) as batch_op:
        batch_op.drop_column('premium_collected')
        batch_op.drop_column('premium_paid')


def downgrade() -> None:
    # Re-add premium columns (will be zero for all existing records)
    with op.batch_alter_table('equity_holdings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('premium_collected', sa.Float(), nullable=False, server_default='0.0'))
        batch_op.add_column(sa.Column('premium_paid', sa.Float(), nullable=False, server_default='0.0'))
