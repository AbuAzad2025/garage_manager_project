from alembic import op
import sqlalchemy as sa

revision = "f71ea1937c8d"
down_revision = "7f31a2c4b9d0"
branch_labels = None
depends_on = None

def upgrade():
    # 1) إضافة العمود (مبدئياً nullable لتسهيل التحويل على SQLite)
    with op.batch_alter_table("permissions") as batch_op:
        batch_op.add_column(sa.Column("code", sa.String(length=100), nullable=True))

    # 2) تعبئة القيم من name بشكل مُطبّع
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        UPDATE permissions
        SET code = LOWER(
            REPLACE(REPLACE(TRIM(name), ' ', '_'), '-', '_')
        )
        WHERE code IS NULL
        """
    )

    # 3) إنشاء UNIQUE constraint بعد ضمان تعبئة القيم
    with op.batch_alter_table("permissions") as batch_op:
        batch_op.create_unique_constraint("uq_permissions_code", ["code"])

    # (اختياري) جعل العمود غير قابل للإفراغ إذا أردت:
    # مع SQLite قد يعاد بناء الجدول؛ batch_alter_table يتكفل بذلك.
    # مع التأكد مسبقاً إن كل الصفوف فيها code غير NULL.
    # with op.batch_alter_table("permissions") as batch_op:
    #     batch_op.alter_column("code", existing_type=sa.String(length=100), nullable=False)

def downgrade():
    with op.batch_alter_table("permissions") as batch_op:
        batch_op.drop_constraint("uq_permissions_code", type_="unique")
        batch_op.drop_column("code")
