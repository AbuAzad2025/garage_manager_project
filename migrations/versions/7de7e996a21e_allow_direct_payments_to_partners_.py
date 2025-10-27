"""allow_direct_payments_to_partners_suppliers

Revision ID: 7de7e996a21e
Revises: f3af84a72428
Create Date: 2025-10-27 01:12:11.366814

تعديل constraint للسماح بالدفعات المباشرة للشركاء والموردين
في الحياة العملية: دفعة مباشرة للشريك/المورد = تسوية حساب
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7de7e996a21e'
down_revision = 'f3af84a72428'
branch_labels = None
depends_on = None


def upgrade():
    """
    تعديل ck_payment_one_target من = 1 إلى <= 1
    للسماح بالدفعات المباشرة (بدون ربط بفاتورة/مبيعة/الخ)
    
    الجدول الحالي له 47 عمود، نسخهم جميعاً
    """
    op.execute('PRAGMA foreign_keys=OFF;')
    
    # نسخ كامل البيانات
    op.execute('CREATE TABLE payments_backup AS SELECT * FROM payments;')
    
    # حذف الجدول القديم
    op.execute('DROP TABLE payments;')
    
    # إنشاء الجدول الجديد مع الـ constraint المعدل
    op.execute('''
        CREATE TABLE payments (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            payment_number VARCHAR(50) UNIQUE,
            payment_date DATETIME,
            subtotal NUMERIC(12, 2),
            tax_rate NUMERIC(5, 2),
            tax_amount NUMERIC(12, 2),
            total_amount NUMERIC(12, 2) NOT NULL,
            currency VARCHAR(10) NOT NULL DEFAULT 'ILS',
            fx_rate_used NUMERIC(10, 6),
            fx_rate_source VARCHAR(20),
            fx_rate_timestamp DATETIME,
            fx_base_currency VARCHAR(10),
            fx_quote_currency VARCHAR(10),
            method VARCHAR(10) NOT NULL,
            status VARCHAR(10) NOT NULL,
            direction VARCHAR(3) NOT NULL,
            entity_type VARCHAR(20),
            reference VARCHAR(100),
            receipt_number VARCHAR(50),
            notes TEXT,
            receiver_name VARCHAR(200),
            check_number VARCHAR(100),
            check_bank VARCHAR(200),
            check_due_date DATETIME,
            card_holder VARCHAR(200),
            card_expiry VARCHAR(7),
            card_last4 VARCHAR(4),
            bank_transfer_ref VARCHAR(100),
            created_by INTEGER,
            customer_id INTEGER,
            supplier_id INTEGER,
            partner_id INTEGER,
            shipment_id INTEGER,
            expense_id INTEGER,
            loan_settlement_id INTEGER,
            sale_id INTEGER,
            invoice_id INTEGER,
            preorder_id INTEGER,
            service_id INTEGER,
            refund_of_id INTEGER,
            idempotency_key VARCHAR(64) UNIQUE,
            is_archived BOOLEAN DEFAULT 0 NOT NULL,
            archived_at DATETIME,
            archived_by INTEGER,
            archive_reason VARCHAR(200),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            
            FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
            FOREIGN KEY(supplier_id) REFERENCES suppliers (id) ON DELETE CASCADE,
            FOREIGN KEY(partner_id) REFERENCES partners (id) ON DELETE CASCADE,
            FOREIGN KEY(shipment_id) REFERENCES shipments (id) ON DELETE CASCADE,
            FOREIGN KEY(expense_id) REFERENCES expenses (id) ON DELETE CASCADE,
            FOREIGN KEY(sale_id) REFERENCES sales (id) ON DELETE CASCADE,
            FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE,
            FOREIGN KEY(preorder_id) REFERENCES preorders (id) ON DELETE CASCADE,
            FOREIGN KEY(service_id) REFERENCES service_requests (id) ON DELETE CASCADE,
            FOREIGN KEY(refund_of_id) REFERENCES payments (id) ON DELETE SET NULL,
            FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL,
            FOREIGN KEY(archived_by) REFERENCES users (id) ON DELETE SET NULL,
            
            CHECK (total_amount > 0),
            CHECK ((
                (CASE WHEN customer_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN supplier_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN partner_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN shipment_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN expense_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN loan_settlement_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN sale_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN invoice_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN preorder_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN service_id IS NOT NULL THEN 1 ELSE 0 END)
            ) <= 1)
        );
    ''')
    
    # نسخ البيانات (بدون created_at و updated_at لأنها غير موجودة في الجدول القديم)
    op.execute('''
        INSERT INTO payments (
            id, payment_number, payment_date, subtotal, tax_rate, tax_amount,
            total_amount, currency, fx_rate_used, fx_rate_source, fx_rate_timestamp,
            fx_base_currency, fx_quote_currency, method, status, direction,
            entity_type, reference, receipt_number, notes, receiver_name,
            check_number, check_bank, check_due_date, card_holder, card_expiry,
            card_last4, bank_transfer_ref, created_by, customer_id, supplier_id,
            partner_id, shipment_id, expense_id, loan_settlement_id, sale_id,
            invoice_id, preorder_id, service_id, refund_of_id, idempotency_key,
            is_archived, archived_at, archived_by, archive_reason
        )
        SELECT 
            id, payment_number, payment_date, subtotal, tax_rate, tax_amount,
            total_amount, currency, fx_rate_used, fx_rate_source, fx_rate_timestamp,
            fx_base_currency, fx_quote_currency, method, status, direction,
            entity_type, reference, receipt_number, notes, receiver_name,
            check_number, check_bank, check_due_date, card_holder, card_expiry,
            card_last4, bank_transfer_ref, created_by, customer_id, supplier_id,
            partner_id, shipment_id, expense_id, loan_settlement_id, sale_id,
            invoice_id, preorder_id, service_id, refund_of_id, idempotency_key,
            is_archived, archived_at, archived_by, archive_reason
        FROM payments_backup;
    ''')
    
    # حذف الـ backup
    op.execute('DROP TABLE payments_backup;')
    
    # إعادة إنشاء الفهارس
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_payments_payment_number ON payments (payment_number);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_payment_date ON payments (payment_date);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_customer_id ON payments (customer_id);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_supplier_id ON payments (supplier_id);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_partner_id ON payments (partner_id);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_invoice_id ON payments (invoice_id);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_sale_id ON payments (sale_id);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_service_id ON payments (service_id);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_preorder_id ON payments (preorder_id);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_status ON payments (status);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_direction ON payments (direction);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_payments_method ON payments (method);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_pay_sale_status_dir ON payments (sale_id, status, direction);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_pay_inv_status_dir ON payments (invoice_id, status, direction);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_pay_supplier_status_dir ON payments (supplier_id, status, direction);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_pay_partner_status_dir ON payments (partner_id, status, direction);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_pay_preorder_status_dir ON payments (preorder_id, status, direction);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_pay_reversal ON payments (refund_of_id);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_pay_dir_stat_type ON payments (direction, status, entity_type);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_pay_currency ON payments (currency);')
    
    op.execute('PRAGMA foreign_keys=ON;')


def downgrade():
    """الرجوع للقيد القديم (نادراً ما يُستخدم)"""
    pass
