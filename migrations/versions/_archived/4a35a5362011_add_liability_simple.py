"""add liability_party simple

Revision ID: 4a35a5362011
Revises: all_in_one_20251031
Create Date: 2025-10-30 17:31:12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4a35a5362011'
down_revision = 'all_in_one_20251031'
branch_labels = None
depends_on = None


def upgrade():
    # إضافة حقل liability_party لجدول sale_return_lines فقط
    with op.batch_alter_table('sale_return_lines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('liability_party', sa.String(length=20), nullable=True))
        batch_op.create_index(batch_op.f('ix_sale_return_lines_liability_party'), ['liability_party'], unique=False)


def downgrade():
    # حذف حقل liability_party
    with op.batch_alter_table('sale_return_lines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sale_return_lines_liability_party'))
        batch_op.drop_column('liability_party')

