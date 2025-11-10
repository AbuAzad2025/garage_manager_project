"""Add recurring invoices

Revision ID: 6ba7684adf28
Revises: 20250103_partner_hybrid
Create Date: 2025-11-03 23:14:55.813608

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '6ba7684adf28'
down_revision = '20250103_partner_hybrid'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_tables = inspector.get_table_names()

    def existing_columns(table_name):
        return {col['name'] for col in inspector.get_columns(table_name)} if table_name in existing_tables else set()

    def existing_indexes(table_name):
        return {idx['name'] for idx in inspector.get_indexes(table_name)} if table_name in existing_tables else set()

    def existing_foreign_keys(table_name):
        return {fk['name'] for fk in inspector.get_foreign_keys(table_name)} if table_name in existing_tables else set()

    if 'recurring_invoice_templates' not in existing_tables:
        op.create_table(
            'recurring_invoice_templates',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('template_name', sa.String(length=200), nullable=False),
            sa.Column('customer_id', sa.Integer(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column('currency', sa.String(length=10), nullable=False),
            sa.Column('tax_rate', sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column('frequency', sa.String(length=20), nullable=False),
            sa.Column('start_date', sa.Date(), nullable=False),
            sa.Column('end_date', sa.Date(), nullable=True),
            sa.Column('next_invoice_date', sa.Date(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
            sa.Column('branch_id', sa.Integer(), nullable=False),
            sa.Column('site_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.CheckConstraint("frequency IN ('DAILY','WEEKLY','MONTHLY','QUARTERLY','YEARLY')", name='ck_recurring_frequency'),
            sa.CheckConstraint('amount >= 0', name='ck_recurring_amount_ge_0'),
            sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
            sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
            sa.ForeignKeyConstraint(['site_id'], ['sites.id']),
            sa.PrimaryKeyConstraint('id')
        )

        with op.batch_alter_table('recurring_invoice_templates', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_recurring_invoice_templates_branch_id'), ['branch_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_templates_created_at'), ['created_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_templates_customer_id'), ['customer_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_templates_frequency'), ['frequency'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_templates_is_active'), ['is_active'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_templates_next_invoice_date'), ['next_invoice_date'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_templates_site_id'), ['site_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_templates_updated_at'), ['updated_at'], unique=False)

    if 'recurring_invoice_schedules' not in existing_tables:
        op.create_table(
            'recurring_invoice_schedules',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('template_id', sa.Integer(), nullable=False),
            sa.Column('invoice_id', sa.Integer(), nullable=True),
            sa.Column('scheduled_date', sa.Date(), nullable=False),
            sa.Column('generated_at', sa.DateTime(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.CheckConstraint("status IN ('PENDING','GENERATED','FAILED','SKIPPED')", name='ck_schedule_status'),
            sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
            sa.ForeignKeyConstraint(['template_id'], ['recurring_invoice_templates.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )

        with op.batch_alter_table('recurring_invoice_schedules', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_recurring_invoice_schedules_created_at'), ['created_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_schedules_invoice_id'), ['invoice_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_schedules_scheduled_date'), ['scheduled_date'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_schedules_status'), ['status'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_schedules_template_id'), ['template_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_recurring_invoice_schedules_updated_at'), ['updated_at'], unique=False)

    return

    # قيود وحقول bank_reconciliations والبقية متوفرة مسبقاً في قاعدة الإنتاج؛ نتجنب تعديلها على SQLite

    if 'ix_branches_code' in existing_indexes('branches'):
        op.drop_index('ix_branches_code', table_name='branches')
    if 'manager_user_id' in existing_columns('branches'):
        op.create_foreign_key(None, 'branches', 'users', ['manager_user_id'], ['id'])
    if 'manager_employee_id' in existing_columns('branches'):
        op.create_foreign_key(None, 'branches', 'employees', ['manager_employee_id'], ['id'])
    if 'archived_by' in existing_columns('branches'):
        op.create_foreign_key(None, 'branches', 'users', ['archived_by'], ['id'])

    with op.batch_alter_table('cost_center_allocations', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cost_center_allocations_created_by', type_='foreignkey')
        batch_op.drop_constraint('fk_cost_center_allocations_updated_by', type_='foreignkey')
        batch_op.drop_column('updated_by')
        batch_op.drop_column('created_by')

    with op.batch_alter_table('cost_centers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cost_centers_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_cost_centers_updated_by'), ['updated_by'], unique=False)
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'])
        batch_op.create_foreign_key(None, 'users', ['updated_by'], ['id'])

    with op.batch_alter_table('currencies', schema=None) as batch_op:
        batch_op.drop_index('ix_currencies_code')
        batch_op.drop_index('ix_currencies_is_active')

    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.drop_index('ix_customers_email')
        batch_op.drop_index('ix_customers_is_active')
        batch_op.drop_index('ix_customers_name')
        batch_op.drop_index('ix_customers_phone')

    with op.batch_alter_table('employee_advance_installments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_employee_advance_installments_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_employee_advance_installments_updated_at'), ['updated_at'], unique=False)
        batch_op.drop_constraint('fk_installments_employee', type_='foreignkey')
        batch_op.drop_constraint('fk_installments_advance', type_='foreignkey')
        batch_op.drop_constraint('fk_installments_salary', type_='foreignkey')
        batch_op.create_foreign_key(None, 'employees', ['employee_id'], ['id'])
        batch_op.create_foreign_key(None, 'expenses', ['advance_expense_id'], ['id'])
        batch_op.create_foreign_key(None, 'expenses', ['paid_in_salary_expense_id'], ['id'])
        batch_op.drop_column('salary_expense_id')

    with op.batch_alter_table('employee_advances', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_employee_advances_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_employee_advances_updated_at'), ['updated_at'], unique=False)
        batch_op.drop_constraint('fk_advances_expense', type_='foreignkey')
        batch_op.drop_constraint('fk_advances_employee', type_='foreignkey')
        batch_op.create_foreign_key(None, 'expenses', ['expense_id'], ['id'])
        batch_op.create_foreign_key(None, 'employees', ['employee_id'], ['id'])

    with op.batch_alter_table('employee_deductions', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=False,
               autoincrement=True)
        batch_op.create_index(batch_op.f('ix_employee_deductions_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_employee_deductions_updated_at'), ['updated_at'], unique=False)
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key(None, 'expenses', ['expense_id'], ['id'])
        batch_op.create_foreign_key(None, 'employees', ['employee_id'], ['id'])

    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.alter_column('branch_id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.create_foreign_key(None, 'branches', ['branch_id'], ['id'])
        batch_op.create_foreign_key(None, 'sites', ['site_id'], ['id'])

    with op.batch_alter_table('expense_types', schema=None) as batch_op:
        batch_op.alter_column('fields_meta',
               existing_type=sa.TEXT(),
               type_=sa.JSON(),
               existing_nullable=True)
        batch_op.drop_index('ix_expense_types_is_active')

    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.alter_column('branch_id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.drop_index('ix_expenses_employee_date')
        batch_op.create_foreign_key(None, 'sites', ['site_id'], ['id'])
        batch_op.create_foreign_key(None, 'branches', ['branch_id'], ['id'])

    with op.batch_alter_table('partners', schema=None) as batch_op:
        batch_op.drop_index('ix_partners_phone_number')

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.alter_column('payment_number',
               existing_type=sa.VARCHAR(length=50),
               nullable=False)
        batch_op.alter_column('payment_date',
               existing_type=sa.DATETIME(),
               nullable=False)
        batch_op.alter_column('method',
               existing_type=sa.VARCHAR(length=10),
               type_=sa.Enum('cash', 'bank', 'card', 'cheque', 'online', name='payment_method', native_enum=False),
               existing_nullable=False)
        batch_op.alter_column('status',
               existing_type=sa.VARCHAR(length=10),
               type_=sa.Enum('PENDING', 'COMPLETED', 'FAILED', 'REFUNDED', 'CANCELLED', name='payment_status', native_enum=False),
               existing_nullable=False)
        batch_op.alter_column('entity_type',
               existing_type=sa.VARCHAR(length=20),
               type_=sa.Enum('CUSTOMER', 'SUPPLIER', 'PARTNER', 'SHIPMENT', 'EXPENSE', 'LOAN', 'SALE', 'INVOICE', 'PREORDER', 'SERVICE', 'MISCELLANEOUS', 'OTHER', name='payment_entity_type', native_enum=False),
               nullable=False)
        batch_op.alter_column('check_bank',
               existing_type=sa.VARCHAR(length=200),
               type_=sa.String(length=100),
               existing_nullable=True)
        batch_op.alter_column('card_holder',
               existing_type=sa.VARCHAR(length=200),
               type_=sa.String(length=100),
               existing_nullable=True)
        batch_op.alter_column('card_expiry',
               existing_type=sa.VARCHAR(length=7),
               type_=sa.String(length=10),
               existing_nullable=True)
        batch_op.drop_index('ix_payments_entity')
        batch_op.create_index(batch_op.f('ix_payments_archived_at'), ['archived_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_archived_by'), ['archived_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_expense_id'), ['expense_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_loan_settlement_id'), ['loan_settlement_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_receipt_number'), ['receipt_number'], unique=True)
        batch_op.create_index(batch_op.f('ix_payments_refund_of_id'), ['refund_of_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_shipment_id'), ['shipment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_updated_at'), ['updated_at'], unique=False)
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'])
        batch_op.create_foreign_key(None, 'users', ['archived_by'], ['id'])
        batch_op.create_foreign_key(None, 'supplier_loan_settlements', ['loan_settlement_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_index('ix_products_commercial_name')
        batch_op.drop_index('ix_products_is_active')
        batch_op.drop_index('ix_products_vehicle_type_id')

    with op.batch_alter_table('project_costs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_project_costs_updated_by', type_='foreignkey')
        batch_op.drop_constraint('fk_project_costs_created_by', type_='foreignkey')
        batch_op.drop_column('updated_by')
        batch_op.drop_column('created_by')

    with op.batch_alter_table('project_phases', schema=None) as batch_op:
        batch_op.drop_constraint('fk_project_phases_created_by', type_='foreignkey')
        batch_op.drop_constraint('fk_project_phases_updated_by', type_='foreignkey')
        batch_op.drop_column('updated_by')
        batch_op.drop_column('created_by')

    with op.batch_alter_table('project_revenues', schema=None) as batch_op:
        batch_op.drop_constraint('fk_project_revenues_updated_by', type_='foreignkey')
        batch_op.drop_constraint('fk_project_revenues_created_by', type_='foreignkey')
        batch_op.drop_column('updated_by')
        batch_op.drop_column('created_by')

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_projects_created_by'), ['created_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_projects_updated_by'), ['updated_by'], unique=False)
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'])
        batch_op.create_foreign_key(None, 'users', ['updated_by'], ['id'])

    with op.batch_alter_table('saas_invoices', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=False,
               autoincrement=True)
        batch_op.drop_index('ix_saas_invoices_due_date')
        batch_op.drop_index('ix_saas_invoices_paid_at')
        batch_op.drop_index('ix_saas_invoices_status')
        batch_op.create_index(batch_op.f('ix_saas_invoices_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_saas_invoices_updated_at'), ['updated_at'], unique=False)
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key(None, 'saas_subscriptions', ['subscription_id'], ['id'])

    with op.batch_alter_table('saas_plans', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=False,
               autoincrement=True)
        batch_op.drop_index('ix_saas_plans_is_active')
        batch_op.drop_index('ix_saas_plans_is_popular')
        batch_op.drop_index('ix_saas_plans_sort_order')
        batch_op.create_index(batch_op.f('ix_saas_plans_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_saas_plans_updated_at'), ['updated_at'], unique=False)
        batch_op.create_unique_constraint(None, ['name'])

    with op.batch_alter_table('saas_subscriptions', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=False,
               autoincrement=True)
        batch_op.drop_index('ix_saas_subscriptions_end_date')
        batch_op.drop_index('ix_saas_subscriptions_start_date')
        batch_op.drop_index('ix_saas_subscriptions_status')
        batch_op.create_index(batch_op.f('ix_saas_subscriptions_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_saas_subscriptions_updated_at'), ['updated_at'], unique=False)
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['cancelled_by'], ['id'])
        batch_op.create_foreign_key(None, 'customers', ['customer_id'], ['id'])
        batch_op.create_foreign_key(None, 'saas_plans', ['plan_id'], ['id'])

    with op.batch_alter_table('sale_return_lines', schema=None) as batch_op:
        batch_op.alter_column('condition',
               existing_type=sa.VARCHAR(length=20),
               type_=sa.Enum('GOOD', 'DAMAGED', 'FOR_REPAIR', 'UNUSABLE', name='return_line_condition', native_enum=False),
               nullable=False,
               existing_server_default=sa.text("'good'"))
        batch_op.alter_column('liability_party',
               existing_type=sa.VARCHAR(length=20),
               type_=sa.Enum('COMPANY', 'SUPPLIER', 'PARTNER', 'CUSTOMER', 'NONE', name='return_liability_party', native_enum=False),
               existing_nullable=True)

    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.drop_index('ix_sales_archived')
        batch_op.drop_index('ix_sales_customer_date')

    with op.batch_alter_table('service_requests', schema=None) as batch_op:
        batch_op.drop_index('ix_service_customer_status_date')
        batch_op.drop_index('ix_service_mechanic_status_date')
        batch_op.drop_index('ix_service_priority_status')
        batch_op.drop_index('ix_service_requests_archived')

    with op.batch_alter_table('shipments', schema=None) as batch_op:
        batch_op.drop_index('ix_shipments_archived')
        batch_op.drop_index('ix_shipments_dest_status_date')

    with op.batch_alter_table('sites', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sites_manager_employee', type_='foreignkey')
        batch_op.drop_constraint('fk_sites_branch', type_='foreignkey')
        batch_op.drop_constraint('fk_sites_manager_user', type_='foreignkey')
        batch_op.drop_constraint('fk_sites_archived_by', type_='foreignkey')
        batch_op.create_foreign_key(None, 'branches', ['branch_id'], ['id'])
        batch_op.create_foreign_key(None, 'users', ['manager_user_id'], ['id'])
        batch_op.create_foreign_key(None, 'users', ['archived_by'], ['id'])
        batch_op.create_foreign_key(None, 'employees', ['manager_employee_id'], ['id'])

    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.drop_index('ix_suppliers_archived')
        batch_op.drop_index('ix_suppliers_name')

    with op.batch_alter_table('user_branches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_branches_updated_at'), ['updated_at'], unique=False)
        batch_op.drop_constraint('fk_user_branches_user', type_='foreignkey')
        batch_op.drop_constraint('fk_user_branches_branch', type_='foreignkey')
        batch_op.create_foreign_key(None, 'branches', ['branch_id'], ['id'])
        batch_op.create_foreign_key(None, 'users', ['user_id'], ['id'])

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_is_active')

    with op.batch_alter_table('warehouses', schema=None) as batch_op:
        batch_op.drop_index('ix_warehouses_is_active')
        batch_op.drop_index('ix_warehouses_parent_id')
        batch_op.drop_index('ix_warehouses_partner_id')
        batch_op.drop_index('ix_warehouses_supplier_id')
        batch_op.create_foreign_key(None, 'branches', ['branch_id'], ['id'])

    # ### end Alembic commands ###


def downgrade():
    pass
