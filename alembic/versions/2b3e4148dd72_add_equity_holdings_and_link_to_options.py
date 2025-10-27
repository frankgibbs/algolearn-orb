"""add_equity_holdings_and_link_to_options

Revision ID: 2b3e4148dd72
Revises: 
Create Date: 2025-10-23 13:50:43.907100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b3e4148dd72'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create equity_holdings table (if it doesn't exist)
    # Using try/except for idempotency since SQLite doesn't support IF NOT EXISTS in Alembic
    try:
        op.create_table('equity_holdings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('purchase_order_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=10), nullable=False),
        sa.Column('total_shares', sa.Integer(), nullable=False),
        sa.Column('original_cost_basis', sa.Float(), nullable=False),
        sa.Column('initial_purchase_date', sa.DateTime(), nullable=False),
        sa.Column('premium_collected', sa.Float(), nullable=False),
        sa.Column('premium_paid', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('exit_date', sa.DateTime(), nullable=True),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('exit_reason', sa.String(length=100), nullable=True),
        sa.Column('realized_pnl', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol')
        )
    except Exception:
        # Table already exists - skip creation
        pass

    # Add equity_holding_id column to existing option_positions table
    with op.batch_alter_table('option_positions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('equity_holding_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_option_positions_equity_holding_id', 'equity_holdings', ['equity_holding_id'], ['id'])


def downgrade() -> None:
    # Remove equity_holding_id column and foreign key from option_positions
    with op.batch_alter_table('option_positions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_option_positions_equity_holding_id', type_='foreignkey')
        batch_op.drop_column('equity_holding_id')

    # Drop equity_holdings table
    op.drop_table('equity_holdings')
