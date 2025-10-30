"""employee_enhancements_hire_date_deductions_advances

Revision ID: employee_enhance_001
Revises: branches_sites_001
Create Date: 2025-10-30 14:00:00.000000

إضافة تاريخ التعيين للموظفين + جداول الخصومات والأقساط
"""
from alembic import op
import sqlalchemy as sa


revision = 'employee_enhance_001'
down_revision = 'branches_sites_001'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1) إضافة hire_date للموظفين
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hire_date', sa.Date(), nullable=True))
        batch_op.create_index('ix_employees_hire_date', ['hire_date'], unique=False)

    # 2) إنشاء جدول employee_deductions
    op.create_table(
        'employee_deductions',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('deduction_type', sa.String(length=50), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default=sa.text("'ILS'")),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('expense_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name='fk_employee_deductions_employee', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['expense_id'], ['expenses.id'], name='fk_employee_deductions_expense', ondelete='SET NULL'),
    )
    op.create_index('ix_employee_deductions_employee_id', 'employee_deductions', ['employee_id'], unique=False)
    op.create_index('ix_employee_deductions_type', 'employee_deductions', ['deduction_type'], unique=False)
    op.create_index('ix_employee_deductions_start_date', 'employee_deductions', ['start_date'], unique=False)
    op.create_index('ix_employee_deductions_end_date', 'employee_deductions', ['end_date'], unique=False)
    op.create_index('ix_employee_deductions_is_active', 'employee_deductions', ['is_active'], unique=False)

    # 3) إنشاء جدول employee_advance_installments
    op.create_table(
        'employee_advance_installments',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('advance_expense_id', sa.Integer(), nullable=False),
        sa.Column('installment_number', sa.Integer(), nullable=False),
        sa.Column('total_installments', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default=sa.text("'ILS'")),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('paid', sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column('paid_date', sa.Date(), nullable=True),
        sa.Column('salary_expense_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name='fk_advance_installments_employee', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['advance_expense_id'], ['expenses.id'], name='fk_advance_installments_advance', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['salary_expense_id'], ['expenses.id'], name='fk_advance_installments_salary', ondelete='SET NULL'),
    )
    op.create_index('ix_advance_installments_employee_id', 'employee_advance_installments', ['employee_id'], unique=False)
    op.create_index('ix_advance_installments_advance_id', 'employee_advance_installments', ['advance_expense_id'], unique=False)
    op.create_index('ix_advance_installments_due_date', 'employee_advance_installments', ['due_date'], unique=False)
    op.create_index('ix_advance_installments_paid', 'employee_advance_installments', ['paid'], unique=False)


def downgrade():
    op.drop_index('ix_advance_installments_paid', table_name='employee_advance_installments')
    op.drop_index('ix_advance_installments_due_date', table_name='employee_advance_installments')
    op.drop_index('ix_advance_installments_advance_id', table_name='employee_advance_installments')
    op.drop_index('ix_advance_installments_employee_id', table_name='employee_advance_installments')
    op.drop_table('employee_advance_installments')

    op.drop_index('ix_employee_deductions_is_active', table_name='employee_deductions')
    op.drop_index('ix_employee_deductions_end_date', table_name='employee_deductions')
    op.drop_index('ix_employee_deductions_start_date', table_name='employee_deductions')
    op.drop_index('ix_employee_deductions_type', table_name='employee_deductions')
    op.drop_index('ix_employee_deductions_employee_id', table_name='employee_deductions')
    op.drop_table('employee_deductions')

    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_index('ix_employees_hire_date')
        batch_op.drop_column('hire_date')

