"""performance indexes critical

Revision ID: 20251116_perf_critical
Revises: 20251115_customer_expenses
Create Date: 2025-11-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '20251116_perf_critical'
down_revision = '20251115_add_customer_to_expenses'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    
    indexes_to_create = [
        ("ix_customers_name", "customers", ["name"]),
        ("ix_customers_phone", "customers", ["phone"]),
        ("ix_customers_is_archived", "customers", ["is_archived"]),
        ("ix_customers_is_active", "customers", ["is_active"]),
        ("ix_customers_category", "customers", ["category"]),
        
        ("ix_sales_sale_date", "sales", ["sale_date"]),
        ("ix_sales_status", "sales", ["status"]),
        ("ix_sales_customer_id", "sales", ["customer_id"]),
        ("ix_sales_is_archived", "sales", ["is_archived"]),
        ("ix_sales_sale_number", "sales", ["sale_number"]),
        ("ix_sales_seller_id", "sales", ["seller_id"]),
        ("ix_sales_seller_employee_id", "sales", ["seller_employee_id"]),
        
        ("ix_products_name", "products", ["name"]),
        ("ix_products_barcode", "products", ["barcode"]),
        ("ix_products_sku", "products", ["sku"]),
        ("ix_products_is_active", "products", ["is_active"]),
        ("ix_products_category_id", "products", ["category_id"]),
        
        ("ix_payments_payment_date", "payments", ["payment_date"]),
        ("ix_payments_status", "payments", ["status"]),
        ("ix_payments_direction", "payments", ["direction"]),
        ("ix_payments_entity_type", "payments", ["entity_type"]),
        ("ix_payments_customer_id", "payments", ["customer_id"]),
        
        ("ix_expenses_date", "expenses", ["date"]),
        ("ix_expenses_type_id", "expenses", ["type_id"]),
        ("ix_expenses_is_archived", "expenses", ["is_archived"]),
        ("ix_expenses_employee_id", "expenses", ["employee_id"]),
        
        ("ix_suppliers_name", "suppliers", ["name"]),
        ("ix_suppliers_phone", "suppliers", ["phone"]),
        ("ix_suppliers_is_archived", "suppliers", ["is_archived"]),
        
        ("ix_stock_levels_product_id", "stock_levels", ["product_id"]),
        ("ix_stock_levels_warehouse_id", "stock_levels", ["warehouse_id"]),
        
        ("ix_sale_lines_sale_id", "sale_lines", ["sale_id"]),
        ("ix_sale_lines_product_id", "sale_lines", ["product_id"]),
        
        ("ix_service_requests_status", "service_requests", ["status"]),
        ("ix_service_requests_customer_id", "service_requests", ["customer_id"]),
        ("ix_service_requests_received_at", "service_requests", ["received_at"]),
        
        ("ix_invoices_customer_id", "invoices", ["customer_id"]),
        ("ix_invoices_invoice_date", "invoices", ["invoice_date"]),
        ("ix_invoices_cancelled_at", "invoices", ["cancelled_at"]),
        
        ("ix_preorders_customer_id", "preorders", ["customer_id"]),
        ("ix_preorders_preorder_date", "preorders", ["preorder_date"]),
        ("ix_preorders_status", "preorders", ["status"]),
        
        ("ix_online_preorders_customer_id", "online_preorders", ["customer_id"]),
        ("ix_online_preorders_payment_status", "online_preorders", ["payment_status"]),
        
        ("ix_sale_returns_customer_id", "sale_returns", ["customer_id"]),
        ("ix_sale_returns_status", "sale_returns", ["status"]),
        
        ("ix_partners_is_archived", "partners", ["is_archived"]),
        
        ("ix_payments_sale_id", "payments", ["sale_id"]),
        ("ix_payments_invoice_id", "payments", ["invoice_id"]),
        ("ix_payments_service_id", "payments", ["service_id"]),
        ("ix_payments_preorder_id", "payments", ["preorder_id"]),
        ("ix_payments_supplier_id", "payments", ["supplier_id"]),
        ("ix_payments_partner_id", "payments", ["partner_id"]),
        
        ("ix_expenses_supplier_id", "expenses", ["supplier_id"]),
        ("ix_expenses_partner_id", "expenses", ["partner_id"]),
        
        ("ix_stock_levels_product_warehouse", "stock_levels", ["product_id", "warehouse_id"]),
    ]
    
    created = 0
    skipped = 0
    
    for idx_name, table, columns in indexes_to_create:
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
                print(f"Error creating {idx_name}: {table}")
            except:
                pass
            skipped += 1
    
    try:
        print(f"Created {created} new indexes")
        if skipped > 0:
            print(f"Skipped {skipped} indexes (already exist)")
    except:
        pass


def downgrade():
    conn = op.get_bind()
    
    indexes_to_drop = [
        "ix_customers_name",
        "ix_customers_phone",
        "ix_customers_is_archived",
        "ix_customers_is_active",
        "ix_customers_category",
        "ix_sales_sale_date",
        "ix_sales_status",
        "ix_sales_customer_id",
        "ix_sales_is_archived",
        "ix_sales_sale_number",
        "ix_sales_seller_id",
        "ix_sales_seller_employee_id",
        "ix_products_name",
        "ix_products_barcode",
        "ix_products_sku",
        "ix_products_is_active",
        "ix_products_category_id",
        "ix_payments_payment_date",
        "ix_payments_status",
        "ix_payments_direction",
        "ix_payments_entity_type",
        "ix_payments_customer_id",
        "ix_expenses_date",
        "ix_expenses_type_id",
        "ix_expenses_is_archived",
        "ix_expenses_employee_id",
        "ix_suppliers_name",
        "ix_suppliers_phone",
        "ix_suppliers_is_archived",
        "ix_stock_levels_product_id",
        "ix_stock_levels_warehouse_id",
        "ix_sale_lines_sale_id",
        "ix_sale_lines_product_id",
        "ix_service_requests_status",
        "ix_service_requests_customer_id",
        "ix_service_requests_received_at",
        "ix_invoices_customer_id",
        "ix_invoices_invoice_date",
        "ix_invoices_cancelled_at",
        "ix_preorders_customer_id",
        "ix_preorders_preorder_date",
        "ix_preorders_status",
        "ix_online_preorders_customer_id",
        "ix_online_preorders_payment_status",
        "ix_sale_returns_customer_id",
        "ix_sale_returns_status",
        "ix_partners_is_archived",
        "ix_payments_sale_id",
        "ix_payments_invoice_id",
        "ix_payments_service_id",
        "ix_payments_preorder_id",
        "ix_payments_supplier_id",
        "ix_payments_partner_id",
        "ix_expenses_supplier_id",
        "ix_expenses_partner_id",
        "ix_stock_levels_product_warehouse",
    ]
    
    for idx_name in indexes_to_drop:
        try:
            conn.execute(sa.text(f"DROP INDEX IF EXISTS {idx_name}"))
        except Exception:
            pass

