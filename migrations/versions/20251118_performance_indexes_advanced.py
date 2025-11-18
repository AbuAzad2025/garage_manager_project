"""performance indexes advanced

Revision ID: 20251118_perf_advanced
Revises: 20251116_perf_critical
Create Date: 2025-11-18 02:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '20251118_perf_advanced'
down_revision = '20251116_perf_critical'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    
    composite_indexes = [
        ("ix_payments_customer_status_dir", "payments", ["customer_id", "status", "direction"]),
        ("ix_payments_customer_dir_date", "payments", ["customer_id", "direction", "payment_date"]),
        ("ix_payments_sale_status_dir", "payments", ["sale_id", "status", "direction"]),
        ("ix_payments_invoice_status_dir", "payments", ["invoice_id", "status", "direction"]),
        ("ix_payments_service_status_dir", "payments", ["service_id", "status", "direction"]),
        ("ix_payments_preorder_status_dir", "payments", ["preorder_id", "status", "direction"]),
        
        ("ix_sales_customer_status_date", "sales", ["customer_id", "status", "sale_date"]),
        ("ix_sales_customer_archived_date", "sales", ["customer_id", "is_archived", "sale_date"]),
        
        ("ix_invoices_customer_cancelled_date", "invoices", ["customer_id", "cancelled_at", "invoice_date"]),
        
        ("ix_service_requests_customer_status_date", "service_requests", ["customer_id", "status", "received_at"]),
        
        ("ix_preorders_customer_status_date", "preorders", ["customer_id", "status", "preorder_date"]),
        
        ("ix_sale_returns_customer_status_date", "sale_returns", ["customer_id", "status", "created_at"]),
        
        ("ix_checks_customer_dir_status", "checks", ["customer_id", "direction", "status"]),
        ("ix_checks_payment_dir_status", "checks", ["payment_id", "direction", "status"]),
        ("ix_checks_customer_status_date", "checks", ["customer_id", "status", "check_date"]),
        
        ("ix_online_preorders_customer_status_date", "online_preorders", ["customer_id", "payment_status", "created_at"]),
    ]
    
    single_indexes = [
        ("ix_payments_is_archived", "payments", ["is_archived"]),
        ("ix_sales_cancelled_at", "sales", ["cancelled_at"]),
        ("ix_invoices_is_archived", "invoices", ["is_archived"]),
        ("ix_service_requests_is_archived", "service_requests", ["is_archived"]),
        ("ix_preorders_is_archived", "preorders", ["is_archived"]),
        ("ix_sale_returns_is_archived", "sale_returns", ["is_archived"]),
        ("ix_checks_customer_id", "checks", ["customer_id"]),
        ("ix_checks_payment_id", "checks", ["payment_id"]),
        ("ix_checks_status", "checks", ["status"]),
        ("ix_checks_direction", "checks", ["direction"]),
        ("ix_online_preorders_is_archived", "online_preorders", ["is_archived"]),
    ]
    
    created = 0
    skipped = 0
    
    all_indexes = composite_indexes + single_indexes
    
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
        print(f"Created {created} new indexes")
        if skipped > 0:
            print(f"Skipped {skipped} indexes (already exist or table missing)")
    except:
        pass


def downgrade():
    conn = op.get_bind()
    
    indexes_to_drop = [
        "ix_payments_customer_status_dir",
        "ix_payments_customer_dir_date",
        "ix_payments_sale_status_dir",
        "ix_payments_invoice_status_dir",
        "ix_payments_service_status_dir",
        "ix_payments_preorder_status_dir",
        "ix_sales_customer_status_date",
        "ix_sales_customer_archived_date",
        "ix_invoices_customer_cancelled_date",
        "ix_service_requests_customer_status_date",
        "ix_preorders_customer_status_date",
        "ix_sale_returns_customer_status_date",
        "ix_checks_customer_dir_status",
        "ix_checks_payment_dir_status",
        "ix_checks_customer_status_date",
        "ix_online_preorders_customer_status_date",
        "ix_payments_is_archived",
        "ix_sales_cancelled_at",
        "ix_invoices_is_archived",
        "ix_service_requests_is_archived",
        "ix_preorders_is_archived",
        "ix_sale_returns_is_archived",
        "ix_checks_customer_id",
        "ix_checks_payment_id",
        "ix_checks_status",
        "ix_checks_direction",
        "ix_online_preorders_is_archived",
    ]
    
    for idx_name in indexes_to_drop:
        try:
            conn.execute(sa.text(f"DROP INDEX IF EXISTS {idx_name}"))
        except Exception:
            pass

