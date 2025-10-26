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
    
    # ═══════════════════════════════════════════════════════════════
    # 1. Archiving Indexes (أولوية عالية) - 8 indexes
    # ═══════════════════════════════════════════════════════════════
    
    # Customers
    op.create_index(
        'ix_customers_archived',
        'customers',
        ['is_archived', 'archived_at'],
        unique=False
    )
    
    # Suppliers
    op.create_index(
        'ix_suppliers_archived',
        'suppliers',
        ['is_archived', 'archived_at'],
        unique=False
    )
    
    # Partners
    op.create_index(
        'ix_partners_archived',
        'partners',
        ['is_archived', 'archived_at'],
        unique=False
    )
    
    # Sales
    op.create_index(
        'ix_sales_archived',
        'sales',
        ['is_archived', 'archived_at'],
        unique=False
    )
    
    # Payments
    op.create_index(
        'ix_payments_archived',
        'payments',
        ['is_archived', 'archived_at'],
        unique=False
    )
    
    # Service Requests
    op.create_index(
        'ix_service_requests_archived',
        'service_requests',
        ['is_archived', 'archived_at'],
        unique=False
    )
    
    # Shipments
    op.create_index(
        'ix_shipments_archived',
        'shipments',
        ['is_archived', 'archived_at'],
        unique=False
    )
    
    # Expenses
    op.create_index(
        'ix_expenses_archived',
        'expenses',
        ['is_archived', 'archived_at'],
        unique=False
    )
    
    # ═══════════════════════════════════════════════════════════════
    # 2. Settlement Indexes (أولوية عالية) - 3 indexes
    # ═══════════════════════════════════════════════════════════════
    
    # Expenses - Partner
    op.create_index(
        'ix_expenses_partner_date',
        'expenses',
        ['partner_id', 'date'],
        unique=False
    )
    
    # Expenses - Shipment
    op.create_index(
        'ix_expenses_shipment_date',
        'expenses',
        ['shipment_id', 'date'],
        unique=False
    )
    
    # Service Requests - Customer Status Date
    op.create_index(
        'ix_service_customer_status_date',
        'service_requests',
        ['customer_id', 'status', 'received_at'],
        unique=False
    )
    
    # ═══════════════════════════════════════════════════════════════
    # 3. Additional Composite Indexes (أولوية متوسطة) - 15 indexes
    # ═══════════════════════════════════════════════════════════════
    
    # Customer Category Active
    op.create_index(
        'ix_customers_category_active',
        'customers',
        ['category', 'is_active'],
        unique=False
    )
    
    # Customer Currency Active
    op.create_index(
        'ix_customers_currency_active',
        'customers',
        ['currency', 'is_active'],
        unique=False
    )
    
    # Service Mechanic Status Date
    op.create_index(
        'ix_service_mechanic_status_date',
        'service_requests',
        ['mechanic_id', 'status', 'received_at'],
        unique=False
    )
    
    # Service Priority Status
    op.create_index(
        'ix_service_priority_status',
        'service_requests',
        ['priority', 'status'],
        unique=False
    )
    
    # Invoice Customer Status Date
    op.create_index(
        'ix_invoices_customer_status_date',
        'invoices',
        ['customer_id', 'status', 'invoice_date'],
        unique=False
    )
    
    # Invoice Due Status
    op.create_index(
        'ix_invoices_due_status',
        'invoices',
        ['due_date', 'status'],
        unique=False
    )
    
    # Invoice Source Customer
    op.create_index(
        'ix_invoices_source_customer',
        'invoices',
        ['source', 'customer_id'],
        unique=False
    )
    
    # Shipment Dest Status Date
    op.create_index(
        'ix_shipments_dest_status_date',
        'shipments',
        ['destination_id', 'status', 'shipment_date'],
        unique=False
    )
    
    # GL Batches Source
    op.create_index(
        'ix_gl_batches_source_type_id',
        'gl_batches',
        ['source_type', 'source_id'],
        unique=False
    )
    
    # GL Batches Entity
    op.create_index(
        'ix_gl_batches_entity_type_id',
        'gl_batches',
        ['entity_type', 'entity_id'],
        unique=False
    )
    
    # GL Batches Status Posted
    op.create_index(
        'ix_gl_batches_status_posted',
        'gl_batches',
        ['status', 'posted_at'],
        unique=False
    )
    
    # Checks Customer Status Date
    op.create_index(
        'ix_checks_customer_status_date',
        'checks',
        ['customer_id', 'status', 'check_due_date'],
        unique=False
    )
    
    # Checks Due Status
    op.create_index(
        'ix_checks_due_status',
        'checks',
        ['check_due_date', 'status'],
        unique=False
    )
    
    # Archive Type ID Date
    op.create_index(
        'ix_archives_type_id_date',
        'archives',
        ['record_type', 'record_id', 'archived_at'],
        unique=False
    )
    
    # Notes Entity Pinned
    op.create_index(
        'ix_notes_entity_type_id_pinned',
        'notes',
        ['entity_type', 'entity_id', 'is_pinned'],
        unique=False
    )


def downgrade():
    """
    إزالة فهارس الأداء - Rollback
    """
    
    # ═══════════════════════════════════════════════════════════════
    # Archiving Indexes
    # ═══════════════════════════════════════════════════════════════
    op.drop_index('ix_customers_archived', table_name='customers')
    op.drop_index('ix_suppliers_archived', table_name='suppliers')
    op.drop_index('ix_partners_archived', table_name='partners')
    op.drop_index('ix_sales_archived', table_name='sales')
    op.drop_index('ix_payments_archived', table_name='payments')
    op.drop_index('ix_service_requests_archived', table_name='service_requests')
    op.drop_index('ix_shipments_archived', table_name='shipments')
    op.drop_index('ix_expenses_archived', table_name='expenses')
    
    # ═══════════════════════════════════════════════════════════════
    # Settlement Indexes
    # ═══════════════════════════════════════════════════════════════
    op.drop_index('ix_expenses_partner_date', table_name='expenses')
    op.drop_index('ix_expenses_shipment_date', table_name='expenses')
    op.drop_index('ix_service_customer_status_date', table_name='service_requests')
    
    # ═══════════════════════════════════════════════════════════════
    # Composite Indexes
    # ═══════════════════════════════════════════════════════════════
    op.drop_index('ix_customers_category_active', table_name='customers')
    op.drop_index('ix_customers_currency_active', table_name='customers')
    op.drop_index('ix_service_mechanic_status_date', table_name='service_requests')
    op.drop_index('ix_service_priority_status', table_name='service_requests')
    op.drop_index('ix_invoices_customer_status_date', table_name='invoices')
    op.drop_index('ix_invoices_due_status', table_name='invoices')
    op.drop_index('ix_invoices_source_customer', table_name='invoices')
    op.drop_index('ix_shipments_dest_status_date', table_name='shipments')
    op.drop_index('ix_gl_batches_source_type_id', table_name='gl_batches')
    op.drop_index('ix_gl_batches_entity_type_id', table_name='gl_batches')
    op.drop_index('ix_gl_batches_status_posted', table_name='gl_batches')
    op.drop_index('ix_checks_customer_status_date', table_name='checks')
    op.drop_index('ix_checks_due_status', table_name='checks')
    op.drop_index('ix_archives_type_id_date', table_name='archives')
    op.drop_index('ix_notes_entity_type_id_pinned', table_name='notes')

