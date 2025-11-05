"""add_cost_center_id_columns

Revision ID: cf92cef96d01
Revises: af9b1f6ad242
Create Date: 2025-11-05 16:12:08.699446

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cf92cef96d01'
down_revision = 'af9b1f6ad242'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('sales', sa.Column('cost_center_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_sales_cost_center_id'), 'sales', ['cost_center_id'])
        op.create_foreign_key('fk_sales_cost_center', 'sales', 'cost_centers', ['cost_center_id'], ['id'])
    except Exception:
        pass
    
    try:
        op.add_column('expenses', sa.Column('cost_center_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_expenses_cost_center_id'), 'expenses', ['cost_center_id'])
        op.create_foreign_key('fk_expenses_cost_center', 'expenses', 'cost_centers', ['cost_center_id'], ['id'])
    except Exception:
        pass
    
    try:
        op.add_column('invoices', sa.Column('cost_center_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_invoices_cost_center_id'), 'invoices', ['cost_center_id'])
        op.create_foreign_key('fk_invoices_cost_center', 'invoices', 'cost_centers', ['cost_center_id'], ['id'])
    except Exception:
        pass


def downgrade():
    try:
        op.drop_constraint('fk_invoices_cost_center', 'invoices', type_='foreignkey')
        op.drop_index(op.f('ix_invoices_cost_center_id'), table_name='invoices')
        op.drop_column('invoices', 'cost_center_id')
    except Exception:
        pass
    
    try:
        op.drop_constraint('fk_expenses_cost_center', 'expenses', type_='foreignkey')
        op.drop_index(op.f('ix_expenses_cost_center_id'), table_name='expenses')
        op.drop_column('expenses', 'cost_center_id')
    except Exception:
        pass
    
    try:
        op.drop_constraint('fk_sales_cost_center', 'sales', type_='foreignkey')
        op.drop_index(op.f('ix_sales_cost_center_id'), table_name='sales')
        op.drop_column('sales', 'cost_center_id')
    except Exception:
        pass
