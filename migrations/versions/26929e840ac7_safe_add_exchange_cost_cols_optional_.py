"""safe: add exchange cost cols (+ optional partner share product_id)

Revision ID: 26929e840ac7
Revises: a1b2c3d4e5f6
Create Date: 2025-08-16 17:02:23.372488

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '26929e840ac7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) exchange_transactions: add unit_cost, is_priced (لا نلعب بـ NOT NULL)
    if "exchange_transactions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("exchange_transactions")}
        with op.batch_alter_table("exchange_transactions") as batch:
            if "unit_cost" not in cols:
                batch.add_column(sa.Column("unit_cost", sa.Numeric(12, 2)))
            if "is_priced" not in cols:
                batch.add_column(sa.Column("is_priced", sa.Boolean()))

    # 2) warehouse_partner_shares: أضف product_id (اختياري) بلا حذف/إسقاط أي FK موجود
    if "warehouse_partner_shares" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("warehouse_partner_shares")}
        fks = {fk["name"] for fk in insp.get_foreign_keys("warehouse_partner_shares") if fk.get("name")}
        idx = {i["name"] for i in insp.get_indexes("warehouse_partner_shares")}

        # أضف العمود product_id إن لم يكن موجودًا
        if "product_id" not in cols:
            op.add_column(
                "warehouse_partner_shares",
                sa.Column("product_id", sa.Integer(), nullable=True),
            )

        # FK على products إن لم يكن موجودًا
        if "fk_wps_product_id_products" not in fks and "product_id" in (c["name"] for c in insp.get_columns("warehouse_partner_shares")):
            op.create_foreign_key(
                "fk_wps_product_id_products",
                "warehouse_partner_shares",
                "products",
                ["product_id"],
                ["id"],
            )

        # فهارس اختيارية
        if "ix_warehouse_partner_shares_product_id" not in idx and "product_id" in cols:
            op.create_index(
                "ix_warehouse_partner_shares_product_id",
                "warehouse_partner_shares",
                ["product_id"],
            )

def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "exchange_transactions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("exchange_transactions")}
        with op.batch_alter_table("exchange_transactions") as batch:
            if "is_priced" in cols:
                batch.drop_column("is_priced")
            if "unit_cost" in cols:
                batch.drop_column("unit_cost")

    if "warehouse_partner_shares" in insp.get_table_names():
        # أسقط الفهرس/الـ FK لو موجودين ثم أسقط العمود (اختياري)
        idx = {i["name"] for i in insp.get_indexes("warehouse_partner_shares")}
        fks = {fk["name"] for fk in insp.get_foreign_keys("warehouse_partner_shares") if fk.get("name")}
        cols = {c["name"] for c in insp.get_columns("warehouse_partner_shares")}

        if "ix_warehouse_partner_shares_product_id" in idx:
            op.drop_index("ix_warehouse_partner_shares_product_id", table_name="warehouse_partner_shares")
        if "fk_wps_product_id_products" in fks:
            op.drop_constraint("fk_wps_product_id_products", "warehouse_partner_shares", type_="foreignkey")
        if "product_id" in cols:
            op.drop_column("warehouse_partner_shares", "product_id")