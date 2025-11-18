"""performance indexes order by

Revision ID: 20251118_perf_order_by
Revises: 20251118_perf_currency
Create Date: 2025-11-18 02:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '20251118_perf_order_by'
down_revision = '20251118_perf_currency'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    
    order_by_indexes = [
        ("ix_customers_created_at", "customers", ["created_at"]),
        ("ix_sales_created_at", "sales", ["created_at"]),
        ("ix_payments_created_at", "payments", ["created_at"]),
        ("ix_invoices_created_at", "invoices", ["created_at"]),
        ("ix_service_requests_created_at", "service_requests", ["created_at"]),
        ("ix_expenses_created_at", "expenses", ["created_at"]),
        ("ix_products_created_at", "products", ["created_at"]),
        ("ix_suppliers_created_at", "suppliers", ["created_at"]),
        ("ix_partners_created_at", "partners", ["created_at"]),
        ("ix_employees_created_at", "employees", ["created_at"]),
    ]
    
    composite_order_indexes = [
        ("ix_sales_date_status", "sales", ["sale_date", "status"]),
        ("ix_payments_date_status_dir", "payments", ["payment_date", "status", "direction"]),
        ("ix_invoices_date_cancelled", "invoices", ["invoice_date", "cancelled_at"]),
        ("ix_service_requests_received_status", "service_requests", ["received_at", "status"]),
        ("ix_expenses_date_type", "expenses", ["date", "type_id"]),
        ("ix_products_name_active", "products", ["name", "is_active"]),
    ]
    
    created = 0
    skipped = 0
    
    all_indexes = order_by_indexes + composite_order_indexes
    
    for idx_name, table, columns in all_indexes:
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
        print(f"Created {created} new order_by indexes")
        if skipped > 0:
            print(f"Skipped {skipped} indexes (already exist or table missing)")
    except:
        pass


def downgrade():
    conn = op.get_bind()
    
    indexes_to_drop = [
        "ix_customers_created_at",
        "ix_sales_created_at",
        "ix_payments_created_at",
        "ix_invoices_created_at",
        "ix_service_requests_created_at",
        "ix_expenses_created_at",
        "ix_products_created_at",
        "ix_suppliers_created_at",
        "ix_partners_created_at",
        "ix_employees_created_at",
        "ix_sales_date_status",
        "ix_payments_date_status_dir",
        "ix_invoices_date_cancelled",
        "ix_service_requests_received_status",
        "ix_expenses_date_type",
        "ix_products_name_active",
    ]
    
    for idx_name in indexes_to_drop:
        try:
            conn.execute(sa.text(f"DROP INDEX IF EXISTS {idx_name}"))
        except Exception:
            pass

