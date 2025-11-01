"""Add missing columns to employee_advance_installments and expenses

Revision ID: 900e81a536d2
Revises: all_in_one_20251031
Create Date: 2025-10-31 20:45:52.444935

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '900e81a536d2'
down_revision = 'all_in_one_20251031'
branch_labels = None
depends_on = None


def upgrade():
    # Check if columns already exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('employee_advance_installments')]
    
    # Add due_date and paid columns if they don't exist
    if 'due_date' not in columns or 'paid' not in columns:
        with op.batch_alter_table('employee_advance_installments', schema=None) as batch_op:
            if 'due_date' not in columns:
                batch_op.add_column(sa.Column('due_date', sa.Date(), nullable=True))
            if 'paid' not in columns:
                batch_op.add_column(sa.Column('paid', sa.Boolean(), nullable=True, server_default='0'))
        
        # Set default values for existing rows
        if 'due_date' not in columns:
            op.execute("UPDATE employee_advance_installments SET due_date = date('now') WHERE due_date IS NULL")
        if 'paid' not in columns:
            op.execute("UPDATE employee_advance_installments SET paid = 0 WHERE paid IS NULL")
        
        # Make columns non-nullable and add indexes
        with op.batch_alter_table('employee_advance_installments', schema=None) as batch_op:
            if 'due_date' not in columns:
                batch_op.alter_column('due_date', existing_type=sa.Date(), nullable=False)
            if 'paid' not in columns:
                batch_op.alter_column('paid', existing_type=sa.Boolean(), nullable=False)
    
    # Add indexes if they don't exist (indexes can be added even if columns exist)
    indexes = [idx['name'] for idx in inspector.get_indexes('employee_advance_installments')]
    with op.batch_alter_table('employee_advance_installments', schema=None) as batch_op:
        if 'ix_employee_advance_installments_due_date' not in indexes:
            batch_op.create_index('ix_employee_advance_installments_due_date', ['due_date'], unique=False)
        if 'ix_employee_advance_installments_paid' not in indexes:
            batch_op.create_index('ix_employee_advance_installments_paid', ['paid'], unique=False)
    
    # Add missing columns to expenses table
    expense_columns = [col['name'] for col in inspector.get_columns('expenses')]
    
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        if 'check_payee' not in expense_columns:
            batch_op.add_column(sa.Column('check_payee', sa.String(200), nullable=True))
        if 'bank_name' not in expense_columns:
            batch_op.add_column(sa.Column('bank_name', sa.String(100), nullable=True))
        if 'account_number' not in expense_columns:
            batch_op.add_column(sa.Column('account_number', sa.String(100), nullable=True))
        if 'account_holder' not in expense_columns:
            batch_op.add_column(sa.Column('account_holder', sa.String(200), nullable=True))


def downgrade():
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_column('account_holder')
        batch_op.drop_column('account_number')
        batch_op.drop_column('bank_name')
        batch_op.drop_column('check_payee')
    
    with op.batch_alter_table('employee_advance_installments', schema=None) as batch_op:
        batch_op.drop_index('ix_employee_advance_installments_paid')
        batch_op.drop_index('ix_employee_advance_installments_due_date')
        batch_op.drop_column('paid')
        batch_op.drop_column('due_date')
