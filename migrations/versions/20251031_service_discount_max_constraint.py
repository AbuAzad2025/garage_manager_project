"""Add discount max constraint for service parts and tasks

Revision ID: 20251031_discount_max
Revises: a2a78189d13c
Create Date: 2025-10-31 23:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251031_discount_max'
down_revision = 'a2a78189d13c'
branch_labels = None
depends_on = None


def upgrade():
    # Add discount max constraints for service_parts
    with op.batch_alter_table('service_parts', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'chk_service_part_discount_max',
            'discount <= quantity * unit_price'
        )
    
    # Add discount max constraints for service_tasks
    with op.batch_alter_table('service_tasks', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'chk_service_task_discount_max',
            'discount <= quantity * unit_price'
        )


def downgrade():
    # Remove discount max constraints
    with op.batch_alter_table('service_tasks', schema=None) as batch_op:
        batch_op.drop_constraint('chk_service_task_discount_max', type_='check')
    
    with op.batch_alter_table('service_parts', schema=None) as batch_op:
        batch_op.drop_constraint('chk_service_part_discount_max', type_='check')

