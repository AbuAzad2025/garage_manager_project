"""Remove balance columns from suppliers and partners tables

Revision ID: remove_balance_cols
Revises: 20251104_expenses_supplier, 5128b489596b
Create Date: 2025-11-05

"""
from alembic import op
import sqlalchemy as sa


revision = 'remove_balance_cols'
down_revision = ('20251104_expenses_supplier', '5128b489596b')
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.drop_column('balance')
    
    with op.batch_alter_table('partners', schema=None) as batch_op:
        batch_op.drop_column('balance')


def downgrade():
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('balance', sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text('0')))
    
    with op.batch_alter_table('partners', schema=None) as batch_op:
        batch_op.add_column(sa.Column('balance', sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text('0')))

