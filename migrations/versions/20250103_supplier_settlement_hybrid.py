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
    with op.batch_alter_table('supplier_settlements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('previous_settlement_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('opening_balance', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('rights_exchange', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('rights_total', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_sales', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_services', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_preorders', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_expenses', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_total', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('payments_out', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('payments_in', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('payments_returns', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('payments_net', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('closing_balance', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('is_approved', sa.Boolean(), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('approved_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(), nullable=True))
        
        batch_op.create_index('ix_supplier_settlements_from_date', ['from_date'], unique=False)
        batch_op.create_index('ix_supplier_settlements_to_date', ['to_date'], unique=False)
        batch_op.create_index('ix_supplier_settlements_previous_settlement_id', ['previous_settlement_id'], unique=False)
        batch_op.create_index('ix_supplier_settlements_is_approved', ['is_approved'], unique=False)
        batch_op.create_foreign_key('fk_supplier_settlements_previous', 'supplier_settlements', ['previous_settlement_id'], ['id'])
        batch_op.create_foreign_key('fk_supplier_settlements_approved_by', 'users', ['approved_by'], ['id'])


def downgrade():
    with op.batch_alter_table('supplier_settlements', schema=None) as batch_op:
        batch_op.drop_constraint('fk_supplier_settlements_approved_by', type_='foreignkey')
        batch_op.drop_constraint('fk_supplier_settlements_previous', type_='foreignkey')
        batch_op.drop_index('ix_supplier_settlements_is_approved')
        batch_op.drop_index('ix_supplier_settlements_previous_settlement_id')
        batch_op.drop_index('ix_supplier_settlements_to_date')
        batch_op.drop_index('ix_supplier_settlements_from_date')
        
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approved_by')
        batch_op.drop_column('is_approved')
        batch_op.drop_column('closing_balance')
        batch_op.drop_column('payments_net')
        batch_op.drop_column('payments_returns')
        batch_op.drop_column('payments_in')
        batch_op.drop_column('payments_out')
        batch_op.drop_column('obligations_total')
        batch_op.drop_column('obligations_expenses')
        batch_op.drop_column('obligations_preorders')
        batch_op.drop_column('obligations_services')
        batch_op.drop_column('obligations_sales')
        batch_op.drop_column('rights_total')
        batch_op.drop_column('rights_exchange')
        batch_op.drop_column('opening_balance')
        batch_op.drop_column('previous_settlement_id')

