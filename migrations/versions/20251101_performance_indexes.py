"""performance indexes

Revision ID: 20251101_perf_idx
Revises: 20251031_discount_max
Create Date: 2025-11-01 10:47:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251101_perf_idx'
down_revision = '20251031_discount_max'
branch_labels = None
depends_on = None


def upgrade():
    # إضافة فهارس الأداء المهمة فقط
    with op.batch_alter_table('employee_advance_installments', schema=None) as batch_op:
        # حذف الفهارس القديمة إذا كانت موجودة
        try:
            batch_op.drop_index('idx_installment_paid_date')
        except:
            pass
        try:
            batch_op.drop_index('idx_installment_salary_link')
        except:
            pass
        try:
            batch_op.drop_index('ix_employee_advance_installments_salary_expense_id')
        except:
            pass
        
        # إضافة فهارس جديدة محسنة
        batch_op.create_index('ix_employee_advance_installments_paid_date', ['paid_date'], unique=False)
        batch_op.create_index('ix_employee_advance_installments_paid_in_salary_expense_id', ['paid_in_salary_expense_id'], unique=False)

    with op.batch_alter_table('payments', schema=None) as batch_op:
        # إضافة فهارس مهمة للأداء
        batch_op.create_index('ix_pay_created_at', ['payment_date'], unique=False)
        batch_op.create_index('ix_pay_direction', ['direction'], unique=False)
        batch_op.create_index('ix_pay_status', ['status'], unique=False)
        batch_op.create_index('ix_payments_entity_type', ['entity_type'], unique=False)
        batch_op.create_index('ix_payments_idempotency_key', ['idempotency_key'], unique=True)
        batch_op.create_index('ix_payments_is_archived', ['is_archived'], unique=False)

    # إضافة فهارس للجداول الأخرى
    with op.batch_alter_table('saas_invoices', schema=None) as batch_op:
        try:
            batch_op.drop_index('ix_saas_invoices_invoice_number')
        except:
            pass
        batch_op.create_index('ix_saas_invoices_invoice_number', ['invoice_number'], unique=True)

    with op.batch_alter_table('user_branches', schema=None) as batch_op:
        batch_op.create_index('ix_user_branches_created_at', ['created_at'], unique=False)


def downgrade():
    # عكس العمليات
    with op.batch_alter_table('user_branches', schema=None) as batch_op:
        try:
            batch_op.drop_index('ix_user_branches_created_at')
        except:
            pass

    with op.batch_alter_table('saas_invoices', schema=None) as batch_op:
        try:
            batch_op.drop_index('ix_saas_invoices_invoice_number')
        except:
            pass

    with op.batch_alter_table('payments', schema=None) as batch_op:
        try:
            batch_op.drop_index('ix_payments_is_archived')
        except:
            pass
        try:
            batch_op.drop_index('ix_payments_idempotency_key')
        except:
            pass
        try:
            batch_op.drop_index('ix_payments_entity_type')
        except:
            pass
        try:
            batch_op.drop_index('ix_pay_status')
        except:
            pass
        try:
            batch_op.drop_index('ix_pay_direction')
        except:
            pass
        try:
            batch_op.drop_index('ix_pay_created_at')
        except:
            pass

    with op.batch_alter_table('employee_advance_installments', schema=None) as batch_op:
        try:
            batch_op.drop_index('ix_employee_advance_installments_paid_in_salary_expense_id')
        except:
            pass
        try:
            batch_op.drop_index('ix_employee_advance_installments_paid_date')
        except:
            pass

