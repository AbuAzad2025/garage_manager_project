"""add check permission fields

Revision ID: 20251119_check_permission_fields
Revises: 20251120_partner_balance_cols
Create Date: 2025-11-19 21:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text


revision = '20251119_check_permission_fields'
down_revision = '6ea86c743936'  # آخر migration في السلسلة
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("checks")}
    is_sqlite = bind.dialect.name == "sqlite"
    
    # إضافة حقل عدد مرات السماح بإعادة الإرسال
    if "resubmit_allowed_count" not in columns:
        if is_sqlite:
            op.execute('ALTER TABLE checks ADD COLUMN resubmit_allowed_count INTEGER NOT NULL DEFAULT 1')
        else:
            op.add_column("checks", sa.Column("resubmit_allowed_count", sa.Integer(), nullable=False, server_default=sa_text("1")))
    
    # إضافة حقل عدد مرات السماح بالرجوع من الحالة القانونية
    if "legal_return_allowed_count" not in columns:
        if is_sqlite:
            op.execute('ALTER TABLE checks ADD COLUMN legal_return_allowed_count INTEGER NOT NULL DEFAULT 1')
        else:
            op.add_column("checks", sa.Column("legal_return_allowed_count", sa.Integer(), nullable=False, server_default=sa_text("1")))
    
    # تحديث القيم الافتراضية للشيكات الموجودة
    try:
        bind.execute(sa_text("""
            UPDATE checks 
            SET resubmit_allowed_count = 1 
            WHERE resubmit_allowed_count IS NULL
        """))
        bind.execute(sa_text("""
            UPDATE checks 
            SET legal_return_allowed_count = 1 
            WHERE legal_return_allowed_count IS NULL
        """))
        bind.commit()
    except Exception:
        bind.rollback()


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("checks")}
    is_sqlite = bind.dialect.name == "sqlite"
    
    if "resubmit_allowed_count" in columns:
        if is_sqlite:
            with op.batch_alter_table("checks") as batch_op:
                batch_op.drop_column("resubmit_allowed_count")
        else:
            op.drop_column("checks", "resubmit_allowed_count")
    
    if "legal_return_allowed_count" in columns:
        if is_sqlite:
            with op.batch_alter_table("checks") as batch_op:
                batch_op.drop_column("legal_return_allowed_count")
        else:
            op.drop_column("checks", "legal_return_allowed_count")

