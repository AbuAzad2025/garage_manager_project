"""add seller_employee_id to sales

Revision ID: 20251108_sales_employee
Revises: 20251104_expenses_supplier
Create Date: 2025-11-08 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20251108_sales_employee'
down_revision = '20251104_expenses_supplier'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sales', sa.Column('seller_employee_id', sa.Integer(), nullable=True))
    op.create_index('ix_sales_seller_employee_id', 'sales', ['seller_employee_id'], unique=False)
    op.create_foreign_key('fk_sales_seller_employee', 'sales', 'employees', ['seller_employee_id'], ['id'], ondelete='SET NULL')
    # ensure at least one branch exists (required for employees.branch_id)
    op.execute(
        """
        INSERT INTO branches (name, code, currency, is_active, created_at, updated_at)
        SELECT 'الفرع الرئيسي', 'MAIN', 'ILS', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM branches)
        """
    )
    # insert default employee "نصر" if missing
    op.execute(
        """
        INSERT INTO employees (name, position, salary, phone, email, bank_name, account_number, currency, branch_id, site_id, notes, created_at, updated_at)
        SELECT 'نصر', 'مندوب مبيعات', 0, NULL, NULL, NULL, NULL, 'ILS', b.id, NULL, 'أضيف تلقائياً لترحيل البيانات', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM branches b
        WHERE b.id = (
            SELECT id FROM branches ORDER BY id ASC LIMIT 1
        )
        AND NOT EXISTS (SELECT 1 FROM employees WHERE name = 'نصر')
        LIMIT 1
        """
    )
    op.execute(
        """
        UPDATE sales
        SET seller_employee_id = (
            SELECT id FROM employees
            WHERE name = 'نصر'
            ORDER BY id ASC
            LIMIT 1
        )
        WHERE seller_employee_id IS NULL
        """
    )


def downgrade():
    op.drop_constraint('fk_sales_seller_employee', 'sales', type_='foreignkey')
    op.drop_index('ix_sales_seller_employee_id', table_name='sales')
    op.drop_column('sales', 'seller_employee_id')
    # remove default employee and branch if they were created by this migration
    op.execute(
        """
        DELETE FROM employees
        WHERE name = 'نصر'
        AND NOT EXISTS (
            SELECT 1 FROM sales WHERE seller_employee_id = employees.id
        )
        """
    )
    op.execute(
        """
        DELETE FROM branches
        WHERE code = 'MAIN'
        AND NOT EXISTS (SELECT 1 FROM employees WHERE branch_id = branches.id)
        """
    )

