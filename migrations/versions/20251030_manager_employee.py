"""إضافة manager_employee_id للفروع والمواقع

Revision ID: manager_employee_001
Revises: expense_types_seed_002
Create Date: 2025-10-30 11:00:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'manager_employee_001'
down_revision = 'expense_types_seed_002'
branch_labels = None
depends_on = None


def upgrade():
    # إضافة manager_employee_id للفروع
    with op.batch_alter_table('branches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('manager_employee_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_branches_manager_employee', 'employees', ['manager_employee_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_branches_manager_employee', ['manager_employee_id'])
    
    # إضافة manager_employee_id للمواقع
    with op.batch_alter_table('sites', schema=None) as batch_op:
        batch_op.add_column(sa.Column('manager_employee_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_sites_manager_employee', 'employees', ['manager_employee_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_sites_manager_employee', ['manager_employee_id'])


def downgrade():
    with op.batch_alter_table('sites', schema=None) as batch_op:
        batch_op.drop_index('ix_sites_manager_employee')
        batch_op.drop_constraint('fk_sites_manager_employee', type_='foreignkey')
        batch_op.drop_column('manager_employee_id')
    
    with op.batch_alter_table('branches', schema=None) as batch_op:
        batch_op.drop_index('ix_branches_manager_employee')
        batch_op.drop_constraint('fk_branches_manager_employee', type_='foreignkey')
        batch_op.drop_column('manager_employee_id')

