"""performance indexes currency

Revision ID: 20251118_perf_currency
Revises: 20251118_perf_advanced
Create Date: 2025-11-18 02:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '20251118_perf_currency'
down_revision = '20251118_perf_advanced'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    
    currency_indexes = [
        ("ix_sales_currency", "sales", ["currency"]),
        ("ix_payments_currency", "payments", ["currency"]),
        ("ix_invoices_currency", "invoices", ["currency"]),
        ("ix_service_requests_currency", "service_requests", ["currency"]),
        ("ix_preorders_currency", "preorders", ["currency"]),
        ("ix_sale_returns_currency", "sale_returns", ["currency"]),
        ("ix_online_preorders_currency", "online_preorders", ["currency"]),
        ("ix_checks_currency", "checks", ["currency"]),
        ("ix_customers_currency", "customers", ["currency"]),
    ]
    
    composite_currency_indexes = [
        ("ix_sales_customer_currency_status", "sales", ["customer_id", "currency", "status"]),
        ("ix_payments_customer_currency_dir", "payments", ["customer_id", "currency", "direction"]),
        ("ix_invoices_customer_currency", "invoices", ["customer_id", "currency"]),
    ]
    
    created = 0
    skipped = 0
    
    all_indexes = currency_indexes + composite_currency_indexes
    
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
        print(f"Created {created} new currency indexes")
        if skipped > 0:
            print(f"Skipped {skipped} indexes (already exist or table missing)")
    except:
        pass


def downgrade():
    conn = op.get_bind()
    
    indexes_to_drop = [
        "ix_sales_currency",
        "ix_payments_currency",
        "ix_invoices_currency",
        "ix_service_requests_currency",
        "ix_preorders_currency",
        "ix_sale_returns_currency",
        "ix_online_preorders_currency",
        "ix_checks_currency",
        "ix_customers_currency",
        "ix_sales_customer_currency_status",
        "ix_payments_customer_currency_dir",
        "ix_invoices_customer_currency",
    ]
    
    for idx_name in indexes_to_drop:
        try:
            conn.execute(sa.text(f"DROP INDEX IF EXISTS {idx_name}"))
        except Exception:
            pass

