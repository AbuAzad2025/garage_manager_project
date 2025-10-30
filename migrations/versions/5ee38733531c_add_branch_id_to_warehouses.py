"""add_branch_id_to_warehouses

Revision ID: 5ee38733531c
Revises: manager_employee_001
Create Date: 2025-10-30 10:32:21.567869

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5ee38733531c'
down_revision = 'manager_employee_001'
branch_labels = None
depends_on = None


def upgrade():
    # إضافة عمود branch_id إلى جدول warehouses (مباشرة بدون batch لتجنب مشكلة FK في SQLite)
    op.execute('PRAGMA foreign_keys = OFF')
    op.add_column('warehouses', sa.Column('branch_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_warehouses_branch_id'), 'warehouses', ['branch_id'], unique=False)
    op.execute('PRAGMA foreign_keys = ON')


def downgrade():
    # حذف عمود branch_id من جدول warehouses
    op.execute('PRAGMA foreign_keys = OFF')
    op.drop_index(op.f('ix_warehouses_branch_id'), table_name='warehouses')
    op.drop_column('warehouses', 'branch_id')
    op.execute('PRAGMA foreign_keys = ON')
