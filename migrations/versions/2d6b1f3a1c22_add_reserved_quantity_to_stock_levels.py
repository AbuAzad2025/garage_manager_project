"""add reserved_quantity to stock_levels"""

from alembic import op
import sqlalchemy as sa

revision = "2d6b1f3a1c22"
down_revision = "35b8e4d1c7aa"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("stock_levels", recreate="auto") as b:
        b.add_column(sa.Column("reserved_quantity", sa.Integer(), nullable=False, server_default="0"))
        try:
            b.create_check_constraint(
                "ck_stock_reserved_non_negative",
                "reserved_quantity >= 0"
            )
        except Exception:
            pass
    with op.batch_alter_table("stock_levels") as b:
        b.alter_column("reserved_quantity", server_default=None)


def downgrade():
    with op.batch_alter_table("stock_levels", recreate="auto") as b:
        try:
            b.drop_constraint("ck_stock_reserved_non_negative", type_="check")
        except Exception:
            pass
        b.drop_column("reserved_quantity")
