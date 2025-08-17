"""enforce non-negative stock_levels.quantity"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8a238376c7fd'
down_revision = '48a32db2d856'  # آخر ريفجن قبل هذا (حسب اللوج اللي ظهر عندك)
branch_labels = None
depends_on = None

def upgrade():
    # صفّر أي NULL قبل فرض NOT NULL
    op.execute("UPDATE stock_levels SET quantity = 0 WHERE quantity IS NULL")

    # SQLite-safe: batch_alter_table
    with op.batch_alter_table('stock_levels', schema=None) as batch_op:
        batch_op.alter_column(
            'quantity',
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text('0'),
        )
        batch_op.create_check_constraint(
            'ck_stock_non_negative',
            'quantity >= 0',
        )

def downgrade():
    with op.batch_alter_table('stock_levels', schema=None) as batch_op:
        batch_op.drop_constraint('ck_stock_non_negative', type_='check')
        batch_op.alter_column(
            'quantity',
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
        )
