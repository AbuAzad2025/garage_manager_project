"""Add mechanic_id to service_requests

Revision ID: 2c240baf4438
Revises: abcdef123456
Create Date: 2025-07-30 20:55:17.139077
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2c240baf4438'
down_revision = 'abcdef123456'
branch_labels = None
depends_on = None


def upgrade():
    # ✅ أزلنا إضافة customer_id لأنه موجود أصلاً
    # إضافة mechanic_id فقط
    op.add_column(
        'service_requests',
        sa.Column('mechanic_id', sa.Integer(), nullable=True)
    )


def downgrade():
    # إزالة mechanic_id فقط
    op.drop_column('service_requests', 'mechanic_id')
