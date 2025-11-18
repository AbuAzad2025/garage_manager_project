"""pagination performance indexes

Revision ID: 20251118_pagination_perf
Revises: 20251118_perf_order_by
Create Date: 2025-11-18 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '20251118_pagination_perf'
down_revision = '20251118_perf_order_by'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    
    pagination_indexes = [
        ("ix_customers_name_archived", "customers", ["name", "is_archived"]),
        ("ix_customers_phone_archived", "customers", ["phone", "is_archived"]),
        ("ix_customers_category_archived", "customers", ["category", "is_archived"]),
        ("ix_customers_is_active_archived", "customers", ["is_active", "is_archived"]),
        
        ("ix_sales_sale_date_archived", "sales", ["sale_date", "is_archived"]),
        ("ix_sales_status_archived_date", "sales", ["status", "is_archived", "sale_date"]),
        ("ix_sales_sale_number_archived", "sales", ["sale_number", "is_archived"]),
        ("ix_sales_total_paid_archived", "sales", ["total_paid", "is_archived"]),
        ("ix_sales_balance_due_archived", "sales", ["balance_due", "is_archived"]),
        
        ("ix_payments_payment_date_archived", "payments", ["payment_date", "is_archived"]),
        ("ix_payments_total_amount_archived", "payments", ["total_amount", "is_archived"]),
        ("ix_payments_entity_type_archived", "payments", ["entity_type", "is_archived"]),
        ("ix_payments_direction_archived", "payments", ["direction", "is_archived"]),
        ("ix_payments_method_archived", "payments", ["method", "is_archived"]),
        ("ix_payments_date_amount", "payments", ["payment_date", "total_amount"]),
        ("ix_payments_date_id", "payments", ["payment_date", "id"]),
        
        ("ix_service_requests_received_at_archived", "service_requests", ["received_at", "is_archived"]),
        ("ix_service_requests_status_archived_date", "service_requests", ["status", "is_archived", "received_at"]),
        ("ix_service_requests_priority_archived", "service_requests", ["priority", "is_archived"]),
        ("ix_service_requests_vehicle_vrn_archived", "service_requests", ["vehicle_vrn", "is_archived"]),
        
        ("ix_expenses_date_archived", "expenses", ["date", "is_archived"]),
        ("ix_expenses_type_archived_date", "expenses", ["type_id", "is_archived", "date"]),
        ("ix_expenses_amount_archived", "expenses", ["amount", "is_archived"]),
        
        ("ix_invoices_invoice_date_archived", "invoices", ["invoice_date", "is_archived"]),
        ("ix_invoices_status_archived_date", "invoices", ["status", "is_archived", "invoice_date"]),
        
        ("ix_preorders_preorder_date_archived", "preorders", ["preorder_date", "is_archived"]),
        ("ix_preorders_status_archived_date", "preorders", ["status", "is_archived", "preorder_date"]),
    ]
    
    created = 0
    skipped = 0
    
    for idx_name, table, columns in pagination_indexes:
        try:
            inspector = sa.inspect(conn)
            
            if table not in inspector.get_table_names():
                skipped += 1
                continue
            
            existing_indexes = inspector.get_indexes(table)
            existing_names = {idx['name'] for idx in existing_indexes}
            
            if idx_name in existing_names:
                skipped += 1
                continue
            
            cols_str = ", ".join(columns)
            sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols_str})"
            conn.execute(sa.text(sql))
            created += 1
        except Exception as e:
            try:
                print(f"Error creating {idx_name} on {table}: {str(e)}")
            except:
                pass
            skipped += 1
    
    try:
        print(f"Created {created} new pagination indexes")
        if skipped > 0:
            print(f"Skipped {skipped} indexes (already exist or table missing)")
    except:
        pass


def downgrade():
    conn = op.get_bind()
    
    indexes_to_drop = [
        "ix_customers_name_archived",
        "ix_customers_phone_archived",
        "ix_customers_category_archived",
        "ix_customers_is_active_archived",
        "ix_sales_sale_date_archived",
        "ix_sales_status_archived_date",
        "ix_sales_sale_number_archived",
        "ix_sales_total_paid_archived",
        "ix_sales_balance_due_archived",
        "ix_payments_payment_date_archived",
        "ix_payments_total_amount_archived",
        "ix_payments_entity_type_archived",
        "ix_payments_direction_archived",
        "ix_payments_method_archived",
        "ix_payments_date_amount",
        "ix_payments_date_id",
        "ix_service_requests_received_at_archived",
        "ix_service_requests_status_archived_date",
        "ix_service_requests_priority_archived",
        "ix_service_requests_vehicle_vrn_archived",
        "ix_expenses_date_archived",
        "ix_expenses_type_archived_date",
        "ix_expenses_amount_archived",
        "ix_invoices_invoice_date_archived",
        "ix_invoices_status_archived_date",
        "ix_preorders_preorder_date_archived",
        "ix_preorders_status_archived_date",
    ]
    
    for idx_name in indexes_to_drop:
        try:
            conn.execute(sa.text(f"DROP INDEX IF EXISTS {idx_name}"))
        except Exception:
            pass

