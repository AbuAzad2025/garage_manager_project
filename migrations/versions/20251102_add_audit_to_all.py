"""Add audit columns to all advanced accounting tables

Revision ID: 20251102_add_audit_to_all
Revises: 20251102_advanced_accounting
Create Date: 2025-11-02 23:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '20251102_add_audit_to_all'
down_revision = '20251102_advanced_accounting'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    
    tables_needing_audit = [
        'bank_statements',
        'bank_transactions',
        'bank_reconciliations',
        'cost_center_allocations',
        'project_phases',
        'project_costs',
        'project_revenues'
    ]
    
    for table_name in tables_needing_audit:
        try:
            connection.execute(sa.text(f'ALTER TABLE {table_name} ADD COLUMN created_by INTEGER'))
        except:
            pass
        try:
            connection.execute(sa.text(f'ALTER TABLE {table_name} ADD COLUMN updated_by INTEGER'))
        except:
            pass


def downgrade():
    pass

