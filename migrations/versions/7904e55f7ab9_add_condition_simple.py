"""add_condition_simple

Revision ID: 7904e55f7ab9
Revises: discount_to_amount_001
Create Date: 2025-10-30 16:03:04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7904e55f7ab9'
down_revision = 'discount_to_amount_001'
branch_labels = None
depends_on = None


def upgrade():
    # إضافة حقل condition لجدول sale_return_lines فقط
    with op.batch_alter_table('sale_return_lines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('condition', sa.String(length=20), nullable=False, server_default='GOOD'))
        batch_op.create_index(batch_op.f('ix_sale_return_lines_condition'), ['condition'], unique=False)


def downgrade():
    # حذف حقل condition
    with op.batch_alter_table('sale_return_lines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sale_return_lines_condition'))
        batch_op.drop_column('condition')
