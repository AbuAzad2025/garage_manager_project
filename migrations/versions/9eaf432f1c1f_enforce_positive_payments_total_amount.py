"""enforce positive payments.total_amount

Revision ID: 9eaf432f1c1f
Revises: 8a238376c7fd
Create Date: 2025-08-11 18:15:55.082057

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9eaf432f1c1f'
down_revision = '8a238376c7fd'
branch_labels = None
depends_on = None


def upgrade():
    # صحّح أي بيانات مخالِفة قبل فرض القيد
    op.execute("UPDATE payments SET total_amount = 1 WHERE total_amount IS NULL OR total_amount <= 0")

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.alter_column(
            'total_amount',
            existing_type=sa.Numeric(10, 2),
            nullable=False,
        )
        batch_op.create_check_constraint(
            'ck_payment_total_positive',
            'total_amount > 0',
        )

def downgrade():
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_constraint('ck_payment_total_positive', type_='check')
        batch_op.alter_column(
            'total_amount',
            existing_type=sa.Numeric(10, 2),
            nullable=True,
        )
