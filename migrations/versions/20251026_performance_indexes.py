"""Add performance indexes for optimization

Revision ID: perf_indexes_001
Revises: 
Create Date: 2025-10-26 03:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'perf_indexes_001'
down_revision = None  # سيتم تحديثه تلقائياً
branch_labels = None
depends_on = None


def upgrade():
    """
    إضافة فهارس الأداء - Performance Indexes
    التحسين المتوقع: 70-85%
    """
    
    # استخدام raw SQL مع IF NOT EXISTS لتجنب أخطاء الفهارس الموجودة
    conn = op.get_bind()
    
    # ═══════════════════════════════════════════════════════════════
    # 1. Archiving Indexes (أولوية عالية) - 8 indexes
    # ═══════════════════════════════════════════════════════════════
    
    # Customers
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_customers_archived ON customers (is_archived, archived_at)"
    ))
    
    # Suppliers
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_suppliers_archived ON suppliers (is_archived, archived_at)"
    ))
    
    # Partners
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_partners_archived ON partners (is_archived, archived_at)"
    ))
    
    # Sales
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_sales_archived ON sales (is_archived, archived_at)"
    ))
    
    # Payments
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_payments_archived ON payments (is_archived, archived_at)"
    ))
    
    # Service Requests
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_service_requests_archived ON service_requests (is_archived, archived_at)"
    ))
    
    # Shipments
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_shipments_archived ON shipments (is_archived, archived_at)"
    ))
    
    # Expenses
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_expenses_archived ON expenses (is_archived, archived_at)"
    ))
    
    # ═══════════════════════════════════════════════════════════════
    # 2. Settlement Indexes (أولوية عالية) - 3 indexes
    # ═══════════════════════════════════════════════════════════════
    
    # Expenses - Partner
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_expenses_partner_date ON expenses (partner_id, date)"
    ))
    
    # Expenses - Shipment
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_expenses_shipment_date ON expenses (shipment_id, date)"
    ))
    
    # Service Requests - Customer Status Date
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_service_customer_status_date ON service_requests (customer_id, status, received_at)"
    ))
    
    # ═══════════════════════════════════════════════════════════════
    # 3. Additional Composite Indexes (أولوية متوسطة) - 15 indexes
    # ═══════════════════════════════════════════════════════════════
    
    # Customer Category Active
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_customers_category_active ON customers (category, is_active)"
    ))
    
    # Customer Currency Active
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_customers_currency_active ON customers (currency, is_active)"
    ))
    
    # Service Mechanic Status Date
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_service_mechanic_status_date ON service_requests (mechanic_id, status, received_at)"
    ))
    
    # Service Priority Status
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_service_priority_status ON service_requests (priority, status)"
    ))
    
    # Invoice Customer Status Date
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_invoices_customer_status_date ON invoices (customer_id, status, invoice_date)"
    ))
    
    # Invoice Due Status
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_invoices_due_status ON invoices (due_date, status)"
    ))
    
    # Invoice Source Customer
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_invoices_source_customer ON invoices (source, customer_id)"
    ))
    
    # Shipment Dest Status Date
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_shipments_dest_status_date ON shipments (destination_id, status, shipment_date)"
    ))
    
    # GL Batches Source
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_gl_batches_source_type_id ON gl_batches (source_type, source_id)"
    ))
    
    # GL Batches Entity
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_gl_batches_entity_type_id ON gl_batches (entity_type, entity_id)"
    ))
    
    # GL Batches Status Posted
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_gl_batches_status_posted ON gl_batches (status, posted_at)"
    ))
    
    # Checks Customer Status Date
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_checks_customer_status_date ON checks (customer_id, status, check_due_date)"
    ))
    
    # Checks Due Status
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_checks_due_status ON checks (check_due_date, status)"
    ))
    
    # Archive Type ID Date
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_archives_type_id_date ON archives (record_type, record_id, archived_at)"
    ))
    
    # Notes Entity Pinned
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_notes_entity_type_id_pinned ON notes (entity_type, entity_id, is_pinned)"
    ))


def downgrade():
    """
    إزالة فهارس الأداء - Rollback
    """
    
    conn = op.get_bind()
    
    # ═══════════════════════════════════════════════════════════════
    # Archiving Indexes
    # ═══════════════════════════════════════════════════════════════
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_customers_archived"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_suppliers_archived"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_partners_archived"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_sales_archived"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_payments_archived"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_service_requests_archived"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_shipments_archived"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_expenses_archived"))
    
    # ═══════════════════════════════════════════════════════════════
    # Settlement Indexes
    # ═══════════════════════════════════════════════════════════════
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_expenses_partner_date"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_expenses_shipment_date"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_service_customer_status_date"))
    
    # ═══════════════════════════════════════════════════════════════
    # Composite Indexes
    # ═══════════════════════════════════════════════════════════════
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_customers_category_active"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_customers_currency_active"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_service_mechanic_status_date"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_service_priority_status"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_invoices_customer_status_date"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_invoices_due_status"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_invoices_source_customer"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_shipments_dest_status_date"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_gl_batches_source_type_id"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_gl_batches_entity_type_id"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_gl_batches_status_posted"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_checks_customer_status_date"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_checks_due_status"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_archives_type_id_date"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_notes_entity_type_id_pinned"))

