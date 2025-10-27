"""remove_invoice_status_column

Revision ID: f3af84a72428
Revises: 8a75a15c043a
Create Date: 2025-10-26 23:59:29.366814

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3af84a72428'
down_revision = '8a75a15c043a'
branch_labels = None
depends_on = None


def upgrade():
    """
    حذف عمود status من جدول invoices
    status أصبح property محسوب تلقائياً من total_paid
    
    نستخدم طريقة إعادة إنشاء الجدول لأن SQLite لا يدعم DROP COLUMN مباشرة
    """
    # الخطوة 0: تعطيل FOREIGN KEY constraints
    op.execute('PRAGMA foreign_keys=OFF;')
    
    # الخطوة 0.5: حذف أي جداول مؤقتة من محاولات سابقة
    op.execute('DROP TABLE IF EXISTS invoices_new;')
    
    # الخطوة 1: حذف الفهارس التي تستخدم status
    op.execute('DROP INDEX IF EXISTS ix_invoices_customer_status_date;')
    op.execute('DROP INDEX IF EXISTS ix_invoices_status;')
    
    # الخطوة 2: إنشاء جدول جديد بدون عمود status
    op.execute('''
        CREATE TABLE invoices_new (
            id INTEGER NOT NULL PRIMARY KEY,
            invoice_number VARCHAR(50) NOT NULL UNIQUE,
            invoice_date DATETIME NOT NULL,
            due_date DATETIME,
            customer_id INTEGER NOT NULL,
            supplier_id INTEGER,
            partner_id INTEGER,
            sale_id INTEGER,
            service_id INTEGER,
            preorder_id INTEGER,
            source VARCHAR(8) NOT NULL,
            kind VARCHAR(11) NOT NULL,
            credit_for_id INTEGER,
            refund_of_id INTEGER,
            currency VARCHAR(10) NOT NULL,
            fx_rate_used NUMERIC(10, 6),
            fx_rate_source VARCHAR(20),
            fx_rate_timestamp DATETIME,
            fx_base_currency VARCHAR(10),
            fx_quote_currency VARCHAR(10),
            total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
            tax_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
            discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
            notes TEXT,
            terms TEXT,
            refunded_total NUMERIC(12, 2) NOT NULL DEFAULT 0,
            idempotency_key VARCHAR(64) UNIQUE,
            cancelled_at DATETIME,
            cancelled_by INTEGER,
            cancel_reason VARCHAR(200),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers (id),
            FOREIGN KEY(supplier_id) REFERENCES suppliers (id),
            FOREIGN KEY(partner_id) REFERENCES partners (id),
            FOREIGN KEY(sale_id) REFERENCES sales (id),
            FOREIGN KEY(service_id) REFERENCES service_requests (id),
            FOREIGN KEY(preorder_id) REFERENCES preorders (id),
            FOREIGN KEY(credit_for_id) REFERENCES invoices (id) ON DELETE SET NULL,
            FOREIGN KEY(refund_of_id) REFERENCES invoices (id) ON DELETE SET NULL,
            FOREIGN KEY(cancelled_by) REFERENCES users (id)
        );
    ''')
    
    # الخطوة 3: نسخ البيانات (بدون عمود status)
    op.execute('''
        INSERT INTO invoices_new (
            id, invoice_number, invoice_date, due_date,
            customer_id, supplier_id, partner_id, sale_id, service_id, preorder_id,
            source, kind, credit_for_id, refund_of_id,
            currency, fx_rate_used, fx_rate_source, fx_rate_timestamp,
            fx_base_currency, fx_quote_currency,
            total_amount, tax_amount, discount_amount, notes, terms,
            refunded_total, idempotency_key,
            cancelled_at, cancelled_by, cancel_reason,
            created_at, updated_at
        )
        SELECT 
            id, invoice_number, invoice_date, due_date,
            customer_id, supplier_id, partner_id, sale_id, service_id, preorder_id,
            source, kind, credit_for_id, refund_of_id,
            currency, fx_rate_used, fx_rate_source, fx_rate_timestamp,
            fx_base_currency, fx_quote_currency,
            total_amount, tax_amount, discount_amount, notes, terms,
            refunded_total, idempotency_key,
            cancelled_at, cancelled_by, cancel_reason,
            created_at, updated_at
        FROM invoices;
    ''')
    
    # الخطوة 4: حذف الجدول القديم
    op.execute('DROP TABLE invoices;')
    
    # الخطوة 5: إعادة تسمية الجدول الجديد
    op.execute('ALTER TABLE invoices_new RENAME TO invoices;')
    
    # الخطوة 6: إعادة إنشاء الفهارس (بدون status)
    op.execute('CREATE INDEX ix_invoices_invoice_number ON invoices (invoice_number);')
    op.execute('CREATE INDEX ix_invoices_invoice_date ON invoices (invoice_date);')
    op.execute('CREATE INDEX ix_invoices_due_date ON invoices (due_date);')
    op.execute('CREATE INDEX ix_invoices_customer_id ON invoices (customer_id);')
    op.execute('CREATE INDEX ix_invoices_supplier_id ON invoices (supplier_id);')
    op.execute('CREATE INDEX ix_invoices_partner_id ON invoices (partner_id);')
    op.execute('CREATE INDEX ix_invoices_sale_id ON invoices (sale_id);')
    op.execute('CREATE INDEX ix_invoices_service_id ON invoices (service_id);')
    op.execute('CREATE INDEX ix_invoices_preorder_id ON invoices (preorder_id);')
    op.execute('CREATE INDEX ix_invoices_source ON invoices (source);')
    op.execute('CREATE INDEX ix_invoices_kind ON invoices (kind);')
    op.execute('CREATE INDEX ix_invoices_cancelled_at ON invoices (cancelled_at);')
    
    # الخطوة 7: إعادة تفعيل FOREIGN KEY constraints
    op.execute('PRAGMA foreign_keys=ON;')


def downgrade():
    """
    إعادة عمود status في حالة الرجوع
    (نادراً ما نحتاج هذا، لكنه موجود للأمان)
    """
    pass  # لن نطبق downgrade لأنه معقد ونادر الاستخدام
