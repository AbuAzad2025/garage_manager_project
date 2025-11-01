"""Allow nullable for Customer email and whatsapp

Revision ID: 8a75a15c043a
Revises: perf_indexes_001
Create Date: 2025-10-26 14:47:01.199531

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a75a15c043a'
down_revision = 'perf_indexes_001'
branch_labels = None
depends_on = None


def upgrade():
    """
    السماح بـ NULL في email و whatsapp للعملاء
    لحل مشكلة UNIQUE constraint مع السلاسل الفارغة
    
    SQLite لا يدعم ALTER COLUMN مباشرة، لذلك نستخدم recreate table
    """
    conn = op.get_bind()
    
    # تعطيل foreign keys مؤقتاً
    conn.execute(sa.text("PRAGMA foreign_keys = OFF"))
    
    # إعادة إنشاء الجدول مع nullable=True
    with op.batch_alter_table('customers', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('email',
                              existing_type=sa.String(length=120),
                              nullable=True,
                              existing_nullable=False)
        batch_op.alter_column('whatsapp',
                              existing_type=sa.String(length=20),
                              nullable=True,
                              existing_nullable=False)
    
    # تحويل السلاسل الفارغة إلى NULL
    conn.execute(sa.text("UPDATE customers SET email = NULL WHERE email = ''"))
    conn.execute(sa.text("UPDATE customers SET whatsapp = NULL WHERE whatsapp = ''"))
    
    # إعادة تفعيل foreign keys
    conn.execute(sa.text("PRAGMA foreign_keys = ON"))


def downgrade():
    """
    إرجاع email و whatsapp إلى NOT NULL
    """
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.alter_column('email',
                              existing_type=sa.String(length=120),
                              nullable=False,
                              existing_nullable=True)
        batch_op.alter_column('whatsapp',
                              existing_type=sa.String(length=20),
                              nullable=False,
                              existing_nullable=True)
