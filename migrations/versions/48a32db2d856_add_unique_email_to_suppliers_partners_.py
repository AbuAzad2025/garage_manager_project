"""add unique email to suppliers/partners/employees

Revision ID: 48a32db2d856
Revises: 461cf1b69577
Create Date: 2025-08-11 11:00:40.735509

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '48a32db2d856'
down_revision = '461cf1b69577'
branch_labels = None
depends_on = None


def upgrade():
    # suppliers.email
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=120), nullable=True))
        batch_op.create_unique_constraint('uq_suppliers_email', ['email'])

    # partners.email
    with op.batch_alter_table('partners', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=120), nullable=True))
        batch_op.create_unique_constraint('uq_partners_email', ['email'])

    # employees.email
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=120), nullable=True))
        batch_op.create_unique_constraint('uq_employees_email', ['email'])


def downgrade():
    # employees
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_constraint('uq_employees_email', type_='unique')
        batch_op.drop_column('email')

    # partners
    with op.batch_alter_table('partners', schema=None) as batch_op:
        batch_op.drop_constraint('uq_partners_email', type_='unique')
        batch_op.drop_column('email')

    # suppliers
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.drop_constraint('uq_suppliers_email', type_='unique')
        batch_op.drop_column('email')
