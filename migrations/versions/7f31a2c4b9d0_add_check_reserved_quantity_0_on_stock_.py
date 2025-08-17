"""add CHECK reserved_quantity >= 0 on stock_levels

Revision ID: 7f31a2c4b9d0
Revises: 2d6b1f3a1c22
Create Date: 2025-08-12 21:30:00
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '7f31a2c4b9d0'
down_revision = '2d6b1f3a1c22'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('stock_levels', schema=None) as batch_op:
        batch_op.create_check_constraint('ck_reserved_non_negative', 'reserved_quantity >= 0')

def downgrade():
    with op.batch_alter_table('stock_levels', schema=None) as batch_op:
        batch_op.drop_constraint('ck_reserved_non_negative', type_='check')
