"""add partner settlement hybrid fields

Revision ID: 20250103_partner_hybrid
Revises: 
Create Date: 2025-01-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = '20250103_partner_hybrid'
down_revision = '20251102_add_audit_to_all'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('partner_settlements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('previous_settlement_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('opening_balance', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('rights_inventory', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('rights_sales_share', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('rights_preorders', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('rights_total', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_sales_to_partner', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_services', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_damaged', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_expenses', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_returns', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('obligations_total', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('payments_out', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('payments_in', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('payments_net', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('closing_balance', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('is_approved', sa.Boolean(), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('approved_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(), nullable=True))
        
        batch_op.create_index('ix_partner_settlements_previous_settlement_id', ['previous_settlement_id'], unique=False)
        batch_op.create_index('ix_partner_settlements_is_approved', ['is_approved'], unique=False)
        batch_op.create_foreign_key('fk_partner_settlements_previous', 'partner_settlements', ['previous_settlement_id'], ['id'])
        batch_op.create_foreign_key('fk_partner_settlements_approved_by', 'users', ['approved_by'], ['id'])


def downgrade():
    with op.batch_alter_table('partner_settlements', schema=None) as batch_op:
        batch_op.drop_constraint('fk_partner_settlements_approved_by', type_='foreignkey')
        batch_op.drop_constraint('fk_partner_settlements_previous', type_='foreignkey')
        batch_op.drop_index('ix_partner_settlements_is_approved')
        batch_op.drop_index('ix_partner_settlements_previous_settlement_id')
        
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approved_by')
        batch_op.drop_column('is_approved')
        batch_op.drop_column('closing_balance')
        batch_op.drop_column('payments_net')
        batch_op.drop_column('payments_in')
        batch_op.drop_column('payments_out')
        batch_op.drop_column('obligations_total')
        batch_op.drop_column('obligations_returns')
        batch_op.drop_column('obligations_expenses')
        batch_op.drop_column('obligations_damaged')
        batch_op.drop_column('obligations_services')
        batch_op.drop_column('obligations_sales_to_partner')
        batch_op.drop_column('rights_total')
        batch_op.drop_column('rights_preorders')
        batch_op.drop_column('rights_sales_share')
        batch_op.drop_column('rights_inventory')
        batch_op.drop_column('opening_balance')
        batch_op.drop_column('previous_settlement_id')

