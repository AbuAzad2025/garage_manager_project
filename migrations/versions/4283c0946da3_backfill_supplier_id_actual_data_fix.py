"""Backfill supplier_id on supplier_loan_settlements from product_supplier_loans"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'      # معرّف حقيقي (اتركه كما وُلِّد)
down_revision = '417d57728f9c'  # هذا هو آخر ريفجن عندك (من رسائل اللوج)
branch_labels = None
depends_on = None


def upgrade():
    # 1) إضافة العمود وجعل loan_id اختياري + FK (باستخدام batch لملاءمة SQLite)
    with op.batch_alter_table('supplier_loan_settlements', recreate='auto') as batch:
        batch.add_column(sa.Column('supplier_id', sa.Integer(), nullable=True))
        batch.alter_column('loan_id', existing_type=sa.Integer(), nullable=True)
        batch.create_foreign_key(
            'fk_sls_supplier_id_suppliers',
            'suppliers',
            ['supplier_id'],
            ['id'],
            ondelete='SET NULL'
        )

    # 2) فهرس
    op.create_index(
        'ix_supplier_loan_settlements_supplier_id',
        'supplier_loan_settlements',
        ['supplier_id'],
        unique=False
    )

    # 3) تعبئة البيانات بعد وجود العمود فعلاً
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE supplier_loan_settlements
        SET supplier_id = (
            SELECT p.supplier_id
            FROM product_supplier_loans p
            WHERE p.id = supplier_loan_settlements.loan_id
        )
        WHERE supplier_id IS NULL
          AND EXISTS (
            SELECT 1
            FROM product_supplier_loans p
            WHERE p.id = supplier_loan_settlements.loan_id
          )
    """))

def downgrade():
    with op.batch_alter_table('supplier_loan_settlements', recreate='auto') as batch:
        batch.drop_constraint('fk_sls_supplier_id_suppliers', type_='foreignkey')
        batch.alter_column('loan_id', existing_type=sa.Integer(), nullable=False)
        batch.drop_column('supplier_id')
    op.drop_index('ix_supplier_loan_settlements_supplier_id', table_name='supplier_loan_settlements')