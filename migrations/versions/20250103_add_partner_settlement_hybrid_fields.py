"""add partner settlement hybrid fields

Revision ID: 20250103_partner_hybrid
Revises: 
Create Date: 2025-01-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import sqlite

revision = '20250103_partner_hybrid'
down_revision = '20251102_add_audit_to_all'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_cols = {col['name'] for col in inspector.get_columns('partner_settlements')}
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('partner_settlements')}
    existing_fks = {fk['name'] for fk in inspector.get_foreign_keys('partner_settlements')}

    def _add_col(name, column):
        if name not in existing_cols:
            op.add_column('partner_settlements', column)

    _add_col('previous_settlement_id', sa.Column('previous_settlement_id', sa.Integer(), nullable=True))
    _add_col('opening_balance', sa.Column('opening_balance', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('rights_inventory', sa.Column('rights_inventory', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('rights_sales_share', sa.Column('rights_sales_share', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('rights_preorders', sa.Column('rights_preorders', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('rights_total', sa.Column('rights_total', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_sales_to_partner', sa.Column('obligations_sales_to_partner', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_services', sa.Column('obligations_services', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_damaged', sa.Column('obligations_damaged', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_expenses', sa.Column('obligations_expenses', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_returns', sa.Column('obligations_returns', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('obligations_total', sa.Column('obligations_total', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('payments_out', sa.Column('payments_out', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('payments_in', sa.Column('payments_in', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('payments_net', sa.Column('payments_net', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('closing_balance', sa.Column('closing_balance', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
    _add_col('is_approved', sa.Column('is_approved', sa.Boolean(), server_default=sa.text('0'), nullable=False))
    _add_col('approved_by', sa.Column('approved_by', sa.Integer(), nullable=True))
    _add_col('approved_at', sa.Column('approved_at', sa.DateTime(), nullable=True))

    if 'ix_partner_settlements_previous_settlement_id' not in existing_indexes:
        op.create_index('ix_partner_settlements_previous_settlement_id', 'partner_settlements', ['previous_settlement_id'], unique=False)
    if 'ix_partner_settlements_is_approved' not in existing_indexes:
        op.create_index('ix_partner_settlements_is_approved', 'partner_settlements', ['is_approved'], unique=False)
    # في SQLite لا يمكن إضافة مفاتيح أجنبية مباشرة على جداول موجودة دون إعادة إنشاء الجدول.
    # بما أن قاعدة البيانات التي جلبناها من الإنتاج تحتوي هذه القيود مسبقاً، نتجنب إعادة إنشائها هنا.


def downgrade():
    # لا نحاول إزالة القيود لأن SQLite لا يدعم ذلك بدون إعادة بناء الجدول.
    op.drop_index('ix_partner_settlements_is_approved', table_name='partner_settlements')
    op.drop_index('ix_partner_settlements_previous_settlement_id', table_name='partner_settlements')
    op.drop_column('partner_settlements', 'approved_at')
    op.drop_column('partner_settlements', 'approved_by')
    op.drop_column('partner_settlements', 'is_approved')
    op.drop_column('partner_settlements', 'closing_balance')
    op.drop_column('partner_settlements', 'payments_net')
    op.drop_column('partner_settlements', 'payments_in')
    op.drop_column('partner_settlements', 'payments_out')
    op.drop_column('partner_settlements', 'obligations_total')
    op.drop_column('partner_settlements', 'obligations_returns')
    op.drop_column('partner_settlements', 'obligations_expenses')
    op.drop_column('partner_settlements', 'obligations_damaged')
    op.drop_column('partner_settlements', 'obligations_services')
    op.drop_column('partner_settlements', 'obligations_sales_to_partner')
    op.drop_column('partner_settlements', 'rights_total')
    op.drop_column('partner_settlements', 'rights_preorders')
    op.drop_column('partner_settlements', 'rights_sales_share')
    op.drop_column('partner_settlements', 'rights_inventory')
    op.drop_column('partner_settlements', 'opening_balance')
    op.drop_column('partner_settlements', 'previous_settlement_id')

