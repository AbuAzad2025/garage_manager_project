"""professional_index_optimization_remove_duplicates_and_conflicts

Revision ID: f2084fc204ec
Revises: 372ec91c89ed
Create Date: 2025-11-24 03:31:16.139904

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2084fc204ec'
down_revision = '372ec91c89ed'
branch_labels = None
depends_on = None


def _drop_index_if_exists(conn, table_name, index_name):
    inspector = sa.inspect(conn)
    if table_name not in inspector.get_table_names():
        return False
    
    existing_indexes = inspector.get_indexes(table_name)
    existing_names = {idx['name'] for idx in existing_indexes}
    
    if index_name not in existing_names:
        return False
    
    try:
        op.drop_index(index_name, table_name=table_name)
        return True
    except Exception:
        return False


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    print("=" * 70)
    print("Professional Index Optimization")
    print("=" * 70)
    
    duplicates_to_remove = [
        ('bank_accounts', 'ix_bank_account_code'),
        ('cost_allocation_executions', 'ix_allocation_exec_date'),
        ('cost_allocation_lines', 'ix_allocation_line_rule'),
        ('cost_allocation_rules', 'ix_allocation_rule_active'),
        ('employee_skills', 'ix_employee_skill_expiry'),
        ('engineering_skills', 'ix_skill_category'),
        ('engineering_tasks', 'ix_eng_task_priority'),
        ('engineering_tasks', 'ix_eng_task_status'),
        ('engineering_teams', 'ix_eng_team_active'),
        ('engineering_teams', 'ix_eng_team_specialty'),
        ('project_risks', 'ix_risk_score'),
        ('engineering_timesheets', 'ix_timesheet_status'),
        ('engineering_timesheets', 'ix_timesheet_task'),
        ('sale_lines', 'ix_sale_line_sale'),
        ('payments', 'ix_payments_status'),
        ('payments', 'ix_payments_refund_of_id'),
        ('payments', 'ix_payments_direction'),
        ('payments', 'ix_payments_payment_date'),
        ('service_parts', 'ix_service_part_partner'),
        ('service_tasks', 'ix_service_task_service'),
    ]
    
    print("\n1. Removing duplicate indexes...")
    removed = 0
    for table_name, index_name in duplicates_to_remove:
        if _drop_index_if_exists(conn, table_name, index_name):
            removed += 1
            print(f"  Removed duplicate: {table_name}.{index_name}")
    
    print(f"Removed {removed} duplicate indexes")
    
    conflicting_single_indexes = [
        ('asset_depreciations', 'ix_asset_depreciations_fiscal_month'),
        ('asset_maintenance', 'ix_asset_maintenance_asset_id'),
        ('bank_reconciliations', 'ix_bank_reconciliations_bank_account_id'),
        ('bank_statements', 'ix_bank_statements_bank_account_id'),
        ('bank_transactions', 'ix_bank_transactions_bank_account_id'),
        ('budget_commitments', 'ix_budget_commitments_budget_id'),
        ('budgets', 'ix_budgets_account_code'),
        ('budgets', 'ix_budgets_branch_id'),
        ('checks', 'ix_checks_check_due_date'),
        ('checks', 'ix_checks_status'),
        ('cost_centers', 'ix_cost_centers_name'),
        ('customers', 'ix_customers_name'),
        ('customers', 'ix_customers_phone'),
        ('expenses', 'ix_expenses_date'),
        ('expenses', 'ix_expenses_type_id'),
        ('invoices', 'ix_invoices_customer_id'),
        ('invoices', 'ix_invoices_status'),
        ('invoices', 'ix_invoices_invoice_date'),
        ('payments', 'ix_payments_customer_id'),
        ('payments', 'ix_payments_supplier_id'),
        ('payments', 'ix_payments_partner_id'),
        ('products', 'ix_products_category_id'),
        ('products', 'ix_products_is_active'),
        ('sales', 'ix_sales_customer_id'),
        ('sales', 'ix_sales_status'),
        ('sales', 'ix_sales_sale_date'),
        ('service_requests', 'ix_service_requests_customer_id'),
        ('service_requests', 'ix_service_requests_status'),
        ('stock_levels', 'ix_stock_levels_product_id'),
        ('stock_levels', 'ix_stock_levels_warehouse_id'),
    ]
    
    print("\n2. Removing conflicting single-column indexes (keeping composite ones)...")
    removed_conflicts = 0
    for table_name, index_name in conflicting_single_indexes:
        if _drop_index_if_exists(conn, table_name, index_name):
            removed_conflicts += 1
    
    print(f"Removed {removed_conflicts} conflicting single-column indexes")
    
    print("\n3. Adding missing expression-based indexes...")
    expression_indexes = [
        ('products', 'uq_products_sku_ci', 'LOWER(sku)', 'sku IS NOT NULL'),
        ('products', 'uq_products_serial_ci', 'LOWER(serial_no)', 'serial_no IS NOT NULL'),
    ]
    
    added = 0
    for table_name, index_name, expression, where_clause in expression_indexes:
        if table_name not in inspector.get_table_names():
            continue
        
        existing_indexes = inspector.get_indexes(table_name)
        existing_names = {idx['name'] for idx in existing_indexes}
        
        if index_name in existing_names:
            continue
        
        try:
            db_columns = {col['name'] for col in inspector.get_columns(table_name)}
            if 'sku' not in db_columns and 'serial_no' not in db_columns:
                continue
            
            sql = f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table_name} ({expression}) WHERE {where_clause}"
            conn.execute(sa.text(sql))
            added += 1
            print(f"  Added: {table_name}.{index_name}")
        except Exception as e:
            print(f"  Failed to add {table_name}.{index_name}: {e}")
    
    print(f"Added {added} expression-based indexes")
    
    try:
        conn.execute(sa.text("PRAGMA optimize"))
        print("\nDatabase optimized successfully")
    except Exception:
        pass
    
    print("=" * 70)
    print(f"SUMMARY: Removed {removed + removed_conflicts} indexes, Added {added} indexes")
    print("=" * 70)


def downgrade():
    pass
