"""add_payment_id_to_checks

Revision ID: a8e34bc7e6bf
Revises: 7de7e996a21e
Create Date: 2025-10-27 18:21:04.455446

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8e34bc7e6bf'
down_revision = '7de7e996a21e'
branch_labels = None
depends_on = None


def upgrade():
    # إضافة عمود payment_id في جدول checks للربط مع جدول payments
    with op.batch_alter_table('checks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_checks_payment_id', ['payment_id'], unique=False)
        batch_op.create_foreign_key('fk_checks_payment_id', 'payments', ['payment_id'], ['id'], ondelete='SET NULL')
    
    # ربط الشيكات الموجودة بالدفعات المطابقة (حسب رقم الشيك)
    op.execute("""
        UPDATE checks 
        SET payment_id = (
            SELECT id FROM payments 
            WHERE payments.check_number = checks.check_number 
            LIMIT 1
        )
        WHERE checks.check_number IS NOT NULL
    """)


def downgrade():
    # إزالة الربط
    with op.batch_alter_table('checks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_checks_payment_id', type_='foreignkey')
        batch_op.drop_index('ix_checks_payment_id')
        batch_op.drop_column('payment_id')
