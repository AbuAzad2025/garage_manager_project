"""extend payment splits with currency metadata

Revision ID: 20251110_payment_split_currency
Revises: 20251108_sales_employee
Create Date: 2025-11-10 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20251110_payment_split_currency"
down_revision = ("20251108_sales_employee", "cf92cef96d01")
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_cols = {col['name'] for col in inspector.get_columns('payment_splits')}

    def _add(name, column):
        if name not in existing_cols:
            op.add_column('payment_splits', column)

    _add('currency', sa.Column('currency', sa.String(length=10), nullable=False, server_default="ILS"))
    _add('converted_amount', sa.Column('converted_amount', sa.Numeric(12, 2), nullable=False, server_default="0"))
    _add('converted_currency', sa.Column('converted_currency', sa.String(length=10), nullable=False, server_default="ILS"))
    _add('fx_rate_used', sa.Column('fx_rate_used', sa.Numeric(10, 6)))
    _add('fx_rate_source', sa.Column('fx_rate_source', sa.String(length=20)))
    _add('fx_rate_timestamp', sa.Column('fx_rate_timestamp', sa.DateTime()))
    _add('fx_base_currency', sa.Column('fx_base_currency', sa.String(length=10)))
    _add('fx_quote_currency', sa.Column('fx_quote_currency', sa.String(length=10)))

    existing_indexes = {idx['name'] for idx in inspector.get_indexes('payment_splits')}
    if 'ix_payment_splits_currency' not in existing_indexes:
        op.create_index('ix_payment_splits_currency', 'payment_splits', ['currency'], unique=False)
    if 'ix_payment_splits_converted_currency' not in existing_indexes:
        op.create_index('ix_payment_splits_converted_currency', 'payment_splits', ['converted_currency'], unique=False)


def downgrade():
    pass

