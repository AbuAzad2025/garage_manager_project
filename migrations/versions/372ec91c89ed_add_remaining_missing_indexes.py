"""add_remaining_missing_indexes

Revision ID: 372ec91c89ed
Revises: 8a0730f0d0d7
Create Date: 2025-11-24 03:27:23.377723

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '372ec91c89ed'
down_revision = '8a0730f0d0d7'
branch_labels = None
depends_on = None


def _create_index_if_not_exists(conn, table_name, index_name, columns):
    inspector = sa.inspect(conn)
    
    if table_name not in inspector.get_table_names():
        return False
    
    existing_indexes = inspector.get_indexes(table_name)
    existing_names = {idx['name'] for idx in existing_indexes}
    
    if index_name in existing_names:
        return False
    
    try:
        db_columns = {col['name'] for col in inspector.get_columns(table_name)}
        for col in columns:
            if col not in db_columns:
                return False
        
        cols_str = ", ".join(columns)
        sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({cols_str})"
        conn.execute(sa.text(sql))
        return True
    except Exception:
        return False


def upgrade():
    conn = op.get_bind()
    
    indexes_to_create = [
        ('supplier_settlements', 'ix_supplier_settlements_created_at', ['created_at']),
        ('supplier_settlements', 'ix_supplier_settlements_mode', ['mode']),
        ('supplier_settlements', 'ix_supplier_settlements_updated_at', ['updated_at']),
        ('partners', 'ix_partners_current_balance', ['current_balance']),
        ('partner_settlements', 'ix_partner_settlements_created_at', ['created_at']),
        ('partner_settlements', 'ix_partner_settlements_updated_at', ['updated_at']),
        ('employee_deductions', 'ix_employee_deductions_expense_id', ['expense_id']),
        ('employee_deductions', 'ix_employee_deductions_start_date', ['start_date']),
        ('employee_deductions', 'ix_employee_deductions_created_at', ['created_at']),
        ('employee_deductions', 'ix_employee_deductions_is_active', ['is_active']),
        ('employee_deductions', 'ix_employee_deductions_employee_id', ['employee_id']),
        ('employee_deductions', 'ix_employee_deductions_updated_at', ['updated_at']),
        ('employee_deductions', 'ix_employee_deductions_end_date', ['end_date']),
        ('employee_deductions', 'ix_employee_deductions_deduction_type', ['deduction_type']),
        ('employee_advances', 'ix_employee_advances_updated_at', ['updated_at']),
        ('employee_advances', 'ix_employee_advances_created_at', ['created_at']),
        ('employee_advance_installments', 'ix_employee_advance_installments_updated_at', ['updated_at']),
        ('employee_advance_installments', 'ix_employee_advance_installments_created_at', ['created_at']),
        ('user_branches', 'ix_user_branches_updated_at', ['updated_at']),
        ('exchange_transactions', 'ix_exchange_supplier', ['supplier_id']),
        ('sales', 'ix_sales_cost_center_id', ['cost_center_id']),
        ('sale_lines', 'ix_sale_line_sale', ['sale_id']),
        ('payments', 'ix_pay_partner_status_dir', ['partner_id', 'status', 'direction']),
        ('payments', 'ix_pay_preorder_status_dir', ['preorder_id', 'status', 'direction']),
        ('payments', 'ix_payments_updated_at', ['updated_at']),
        ('payments', 'ix_pay_reversal', ['refund_of_id']),
        ('payments', 'ix_pay_dir_stat_type', ['direction', 'status', 'entity_type']),
        ('payments', 'ix_pay_status', ['status']),
        ('payments', 'ix_pay_direction', ['direction']),
        ('payments', 'ix_pay_currency', ['currency']),
        ('payments', 'ix_pay_created_at', ['payment_date']),
        ('payments', 'ix_pay_sale_status_dir', ['sale_id', 'status', 'direction']),
        ('payments', 'ix_pay_inv_status_dir', ['invoice_id', 'status', 'direction']),
        ('payments', 'ix_pay_supplier_status_dir', ['supplier_id', 'status', 'direction']),
        ('payment_splits', 'ix_payment_splits_payment_id', ['payment_id']),
        ('payment_splits', 'ix_payment_splits_method', ['method']),
        ('service_requests', 'ix_service_requests_cost_center_id', ['cost_center_id']),
        ('service_parts', 'ix_service_part_partner', ['partner_id']),
        ('service_tasks', 'ix_service_task_service', ['service_id']),
        ('online_payments', 'ix_online_payments_idempotency_key', ['idempotency_key']),
        ('online_payments', 'ix_online_payments_payment_id', ['payment_id']),
        ('online_payments', 'ix_online_payments_order_id', ['order_id']),
        ('online_payments', 'ix_online_payments_card_last4', ['card_last4']),
        ('online_payments', 'ix_online_payments_status', ['status']),
        ('online_payments', 'ix_online_payments_updated_at', ['updated_at']),
        ('online_payments', 'ix_online_payments_card_fingerprint', ['card_fingerprint']),
        ('online_payments', 'ix_online_payments_gateway_status', ['gateway', 'status']),
        ('online_payments', 'ix_online_payments_created_at', ['created_at']),
        ('online_payments', 'ix_online_payments_payment_ref', ['payment_ref']),
        ('online_payments', 'ix_online_payments_order_status', ['order_id', 'status']),
        ('expenses', 'ix_expenses_customer_id', ['customer_id']),
        ('expenses', 'ix_expenses_cost_center_id', ['cost_center_id']),
        ('saas_plans', 'ix_saas_plans_updated_at', ['updated_at']),
        ('saas_plans', 'ix_saas_plans_created_at', ['created_at']),
        ('saas_subscriptions', 'ix_saas_subscriptions_created_at', ['created_at']),
        ('saas_subscriptions', 'ix_saas_subscriptions_updated_at', ['updated_at']),
        ('saas_invoices', 'ix_saas_invoices_created_at', ['created_at']),
        ('saas_invoices', 'ix_saas_invoices_updated_at', ['updated_at']),
        ('projects', 'ix_projects_created_by', ['created_by']),
        ('projects', 'ix_projects_updated_by', ['updated_by']),
        ('project_risks', 'ix_risk_score', ['risk_score']),
        ('engineering_teams', 'ix_eng_team_active', ['is_active']),
        ('engineering_teams', 'ix_eng_team_specialty', ['specialty']),
        ('engineering_skills', 'ix_skill_category', ['category']),
        ('employee_skills', 'ix_employee_skill_expiry', ['expiry_date']),
        ('engineering_tasks', 'ix_eng_task_status', ['status']),
        ('engineering_tasks', 'ix_eng_task_priority', ['priority']),
        ('engineering_timesheets', 'ix_timesheet_status', ['status']),
        ('engineering_timesheets', 'ix_timesheet_task', ['task_id']),
    ]
    
    expression_indexes = [
        ('products', 'uq_products_sku_ci', 'LOWER(sku)', 'sku IS NOT NULL'),
        ('products', 'uq_products_serial_ci', 'LOWER(serial_no)', 'serial_no IS NOT NULL'),
    ]
    
    created = 0
    skipped = 0
    
    for table_name, index_name, columns in indexes_to_create:
        if _create_index_if_not_exists(conn, table_name, index_name, columns):
            created += 1
        else:
            skipped += 1
    
    for table_name, index_name, expression, where_clause in expression_indexes:
        inspector = sa.inspect(conn)
        if table_name not in inspector.get_table_names():
            skipped += 1
            continue
        
        existing_indexes = inspector.get_indexes(table_name)
        existing_names = {idx['name'] for idx in existing_indexes}
        
        if index_name in existing_names:
            skipped += 1
            continue
        
        try:
            db_columns = {col['name'] for col in inspector.get_columns(table_name)}
            if 'sku' not in db_columns and 'serial_no' not in db_columns:
                skipped += 1
                continue
            
            sql = f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table_name} ({expression}) WHERE {where_clause}"
            conn.execute(sa.text(sql))
            created += 1
        except Exception:
            skipped += 1
    
    try:
        conn.execute(sa.text("PRAGMA optimize"))
    except Exception:
        pass
    
    try:
        print(f"Created {created} new indexes")
        if skipped > 0:
            print(f"Skipped {skipped} indexes (already exist, table missing, or columns missing)")
    except:
        pass


def downgrade():
    pass
