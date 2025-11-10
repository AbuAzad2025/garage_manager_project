"""add supplier settlement hybrid fields

Revision ID: 20250103_supplier_hybrid
Revises: 
Create Date: 2025-01-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = '20250103_supplier_hybrid'
down_revision = '6ba7684adf28'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_cols = {col['name'] for col in inspector.get_columns('supplier_settlements')}
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('supplier_settlements')}
    existing_fks = {fk['name'] for fk in inspector.get_foreign_keys('supplier_settlements')}

    def _add_col(name, column):
        if name not in existing_cols:
            op.add_column('supplier_settlements', column)

    _add_col('previous_settlement_id', sa.Column('previous_settlement_id', sa.Integer(), nullable=True))
    _add_col('opening_balance', sa.Column('opening_balance', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('rights_exchange', sa.Column('rights_exchange', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('rights_total', sa.Column('rights_total', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_sales', sa.Column('obligations_sales', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_services', sa.Column('obligations_services', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_preorders', sa.Column('obligations_preorders', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_expenses', sa.Column('obligations_expenses', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_total', sa.Column('obligations_total', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('payments_out', sa.Column('payments_out', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('payments_in', sa.Column('payments_in', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('payments_returns', sa.Column('payments_returns', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('payments_net', sa.Column('payments_net', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('closing_balance', sa.Column('closing_balance', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('is_approved', sa.Column('is_approved', sa.Boolean(), server_default=sa.text('0'), nullable=False))
    _add_col('approved_by', sa.Column('approved_by', sa.Integer(), nullable=True))
    _add_col('approved_at', sa.Column('approved_at', sa.DateTime(), nullable=True))

    if 'ix_supplier_settlements_from_date' not in existing_indexes:
        op.create_index('ix_supplier_settlements_from_date', 'supplier_settlements', ['from_date'], unique=False)
    if 'ix_supplier_settlements_to_date' not in existing_indexes:
        op.create_index('ix_supplier_settlements_to_date', 'supplier_settlements', ['to_date'], unique=False)
    if 'ix_supplier_settlements_previous_settlement_id' not in existing_indexes:
        op.create_index('ix_supplier_settlements_previous_settlement_id', 'supplier_settlements', ['previous_settlement_id'], unique=False)
    if 'ix_supplier_settlements_is_approved' not in existing_indexes:
        op.create_index('ix_supplier_settlements_is_approved', 'supplier_settlements', ['is_approved'], unique=False)


def downgrade():
    pass

