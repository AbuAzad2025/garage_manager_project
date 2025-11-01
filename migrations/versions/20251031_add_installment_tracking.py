"""add installment tracking fields

Revision ID: 20251031_installment
Revises: all_in_one_20251031
Create Date: 2025-10-31 20:40:00

"""
from alembic import op
import sqlalchemy as sa


revision = '20251031_installment'
down_revision = 'all_in_one_20251031'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('employee_advance_installments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('paid_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('paid_in_salary_expense_id', sa.Integer(), nullable=True))
        batch_op.create_index('idx_installment_paid_date', ['paid_date'], unique=False)
        batch_op.create_index('idx_installment_salary_link', ['paid_in_salary_expense_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_installment_salary_expense',
            'expenses',
            ['paid_in_salary_expense_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade():
    with op.batch_alter_table('employee_advance_installments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_installment_salary_expense', type_='foreignkey')
        batch_op.drop_index('idx_installment_salary_link')
        batch_op.drop_index('idx_installment_paid_date')
        batch_op.drop_column('paid_in_salary_expense_id')
        batch_op.drop_column('paid_date')

