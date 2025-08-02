"""add balance to customers

Revision ID: abcdef123456
Revises: 9f681d65c5d6
Create Date: 2025-07-29 15:33:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# معرفات Alembic
revision = 'abcdef123456'
down_revision = '9f681d65c5d6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1) إضافة عمود balance إذا لم يكن موجودًا (خاص بـ SQLite)
    if dialect == 'sqlite':
        # نستعلم عن أعمدة الجدول
        existing = bind.execute(text("PRAGMA table_info(customers)")).fetchall()
        cols = [row[1] for row in existing]  # العمود الثاني في النتائج هو اسم العمود
        if 'balance' not in cols:
            op.add_column(
                'customers',
                sa.Column('balance', sa.Numeric(12, 2), nullable=False, server_default='0')
            )
    else:
        # لجميع الديالكـتات الأخرى (Postgres، MySQL...)
        op.add_column(
            'customers',
            sa.Column('balance', sa.Numeric(12, 2), nullable=False, server_default='0')
        )
        # نزيل الـ server_default بعد الإضافة
        op.alter_column('customers', 'balance', server_default=None)

    # 2) على PostgreSQL فقط: إنشاء الدالة والتريجرات لتحديث الرصيد آليًا
    if dialect == 'postgresql':
        # دالة PL/pgSQL
        op.execute(text("""
        CREATE OR REPLACE FUNCTION update_customer_balance()
        RETURNS TRIGGER AS $$
        BEGIN
          IF TG_TABLE_NAME = 'invoices' THEN
            IF TG_OP = 'INSERT' AND NEW.status <> 'CANCELLED' THEN
              UPDATE customers
                SET balance = balance + NEW.total_amount
              WHERE id = NEW.customer_id;
            ELSIF TG_OP = 'UPDATE' THEN
              UPDATE customers
                SET balance = balance
                  + COALESCE((CASE WHEN NEW.status <> 'CANCELLED' THEN NEW.total_amount ELSE 0 END), 0)
                  - COALESCE((CASE WHEN OLD.status <> 'CANCELLED' THEN OLD.total_amount ELSE 0 END), 0)
              WHERE id = NEW.customer_id;
            ELSIF TG_OP = 'DELETE' AND OLD.status <> 'CANCELLED' THEN
              UPDATE customers
                SET balance = balance - OLD.total_amount
              WHERE id = OLD.customer_id;
            END IF;

          ELSIF TG_TABLE_NAME = 'payments' THEN
            IF TG_OP = 'INSERT' AND NEW.status = 'COMPLETED' THEN
              UPDATE customers
                SET balance = balance - NEW.amount
              WHERE id = NEW.customer_id;
            ELSIF TG_OP = 'UPDATE' THEN
              UPDATE customers
                SET balance = balance
                  - COALESCE((CASE WHEN NEW.status = 'COMPLETED' THEN NEW.amount ELSE 0 END), 0)
                  + COALESCE((CASE WHEN OLD.status = 'COMPLETED' THEN OLD.amount ELSE 0 END), 0)
              WHERE id = NEW.customer_id;
            ELSIF TG_OP = 'DELETE' AND OLD.status = 'COMPLETED' THEN
              UPDATE customers
                SET balance = balance + OLD.amount
              WHERE id = OLD.customer_id;
            END IF;
          END IF;

          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """))

        # تريجر على فواتير invoices
        op.execute(text("""
        CREATE TRIGGER trg_invoice_balance
          AFTER INSERT OR UPDATE OR DELETE ON invoices
          FOR EACH ROW EXECUTE FUNCTION update_customer_balance();
        """))

        # تريجر على دفعات payments
        op.execute(text("""
        CREATE TRIGGER trg_payment_balance
          AFTER INSERT OR UPDATE OR DELETE ON payments
          FOR EACH ROW EXECUTE FUNCTION update_customer_balance();
        """))


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1) في PostgreSQL فقط: حذف التريجرات والدالة
    if dialect == 'postgresql':
        op.execute(text("DROP TRIGGER IF EXISTS trg_invoice_balance ON invoices;"))
        op.execute(text("DROP TRIGGER IF EXISTS trg_payment_balance ON payments;"))
        op.execute(text("DROP FUNCTION IF EXISTS update_customer_balance();"))

    # 2) إسقاط عمود balance في جميع الديالكـتات
    op.drop_column('customers', 'balance')
