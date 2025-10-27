"""remove_unrealized_pnl_from_option_positions

Revision ID: 4d6g7350ff94
Revises: 3c5f6259ee83
Create Date: 2025-10-24 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d6g7350ff94'
down_revision: Union[str, None] = '3c5f6259ee83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop unrealized_pnl column from option_positions table
    # Unrealized P&L should be calculated on-demand using get_option_quote MCP tool
    with op.batch_alter_table('option_positions', schema=None) as batch_op:
        batch_op.drop_column('unrealized_pnl')


def downgrade() -> None:
    # Re-add unrealized_pnl column (will be zero for all existing records)
    with op.batch_alter_table('option_positions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('unrealized_pnl', sa.Float(), nullable=True, server_default='0.0'))
