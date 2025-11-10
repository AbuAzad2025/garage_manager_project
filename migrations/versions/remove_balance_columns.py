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
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    supplier_cols = {col['name'] for col in inspector.get_columns('suppliers')}
    if 'balance' in supplier_cols:
        op.drop_column('suppliers', 'balance')

    partner_cols = {col['name'] for col in inspector.get_columns('partners')}
    if 'balance' in partner_cols:
        op.drop_column('partners', 'balance')


def downgrade():
    pass

