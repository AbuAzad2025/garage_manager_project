"""add supplier_id and disbursed_by to expenses

Revision ID: 20251104_expenses_supplier
Revises: 20251102_advanced_accounting
Create Date: 2025-11-04 18:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '20251104_expenses_supplier'
down_revision = '20251102_advanced_accounting'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('supplier_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('disbursed_by', sa.String(length=200), nullable=True))
        batch_op.create_index('ix_expense_supplier_date', ['supplier_id', 'date'], unique=False)
        batch_op.create_foreign_key('fk_expenses_supplier_id', 'suppliers', ['supplier_id'], ['id'], ondelete='SET NULL')
        batch_op.drop_constraint('ck_expense_payee_type_allowed', type_='check')
        batch_op.create_check_constraint('ck_expense_payee_type_allowed', "payee_type IN ('EMPLOYEE','SUPPLIER','PARTNER','UTILITY','OTHER')")


def downgrade():
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_constraint('fk_expenses_supplier_id', type_='foreignkey')
        batch_op.drop_index('ix_expense_supplier_date')
        batch_op.drop_column('disbursed_by')
        batch_op.drop_column('supplier_id')
        batch_op.drop_constraint('ck_expense_payee_type_allowed', type_='check')
        batch_op.create_check_constraint('ck_expense_payee_type_allowed', "payee_type IN ('EMPLOYEE','SUPPLIER','UTILITY','OTHER')")

