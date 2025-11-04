"""Advanced Accounting Modules - Bank, Cost Centers, Projects

Revision ID: 20251102_advanced_accounting
Revises: 20251101_budget_assets_clean
Create Date: 2025-11-02 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '20251102_advanced_accounting'
down_revision = '20251101_budget_assets_clean'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('bank_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('bank_name', sa.String(length=200), nullable=False),
        sa.Column('account_number', sa.String(length=100), nullable=False),
        sa.Column('iban', sa.String(length=50), nullable=True),
        sa.Column('swift_code', sa.String(length=20), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('gl_account_code', sa.String(length=50), nullable=False),
        sa.Column('opening_balance', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('current_balance', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.UniqueConstraint('account_number')
    )
    op.create_index(op.f('ix_bank_accounts_currency'), 'bank_accounts', ['currency'], unique=False)
    op.create_index(op.f('ix_bank_accounts_is_active'), 'bank_accounts', ['is_active'], unique=False)
    op.create_index(op.f('ix_bank_accounts_gl_account_code'), 'bank_accounts', ['gl_account_code'], unique=False)

    op.create_table('bank_statements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('statement_number', sa.String(length=100), nullable=False),
        sa.Column('statement_date', sa.Date(), nullable=False),
        sa.Column('opening_balance', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('closing_balance', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bank_statements_statement_date'), 'bank_statements', ['statement_date'], unique=False)

    op.create_table('bank_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('statement_id', sa.Integer(), nullable=True),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('debit', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('credit', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('matched', sa.Boolean(), nullable=False),
        sa.Column('matched_payment_id', sa.Integer(), nullable=True),
        sa.Column('reconciliation_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ),
        sa.ForeignKeyConstraint(['statement_id'], ['bank_statements.id'], ),
        sa.ForeignKeyConstraint(['matched_payment_id'], ['payments.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bank_transactions_transaction_date'), 'bank_transactions', ['transaction_date'], unique=False)
    op.create_index(op.f('ix_bank_transactions_matched'), 'bank_transactions', ['matched'], unique=False)

    op.create_table('bank_reconciliations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('reconciliation_number', sa.String(length=50), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('book_balance', sa.Float(), nullable=False),
        sa.Column('bank_balance', sa.Float(), nullable=False),
        sa.Column('reconciled_by', sa.Integer(), nullable=True),
        sa.Column('reconciled_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ),
        sa.ForeignKeyConstraint(['reconciled_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reconciliation_number')
    )
    op.create_index(op.f('ix_bank_reconciliations_status'), 'bank_reconciliations', ['status'], unique=False)

    op.create_table('cost_centers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('manager_name', sa.String(length=200), nullable=True),
        sa.Column('budget', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('gl_account_code', sa.String(length=50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['cost_centers.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_cost_centers_is_active'), 'cost_centers', ['is_active'], unique=False)

    op.create_table('cost_center_allocations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cost_center_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('allocation_date', sa.Date(), nullable=False),
        sa.Column('reference_type', sa.String(length=50), nullable=True),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('allocated_by', sa.Integer(), nullable=True),
        sa.Column('allocated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id'], ),
        sa.ForeignKeyConstraint(['allocated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cost_center_allocations_allocation_date'), 'cost_center_allocations', ['allocation_date'], unique=False)

    op.create_table('projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('cost_center_id', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('estimated_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('estimated_revenue', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('actual_cost', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('actual_revenue', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('contract_value', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)
    op.create_index(op.f('ix_projects_start_date'), 'projects', ['start_date'], unique=False)

    op.create_table('project_phases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('phase_number', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('estimated_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('actual_cost', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('project_costs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('phase_id', sa.Integer(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('cost_date', sa.Date(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('reference_type', sa.String(length=50), nullable=True),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('recorded_by', sa.Integer(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['phase_id'], ['project_phases.id'], ),
        sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_costs_cost_date'), 'project_costs', ['cost_date'], unique=False)

    op.create_table('project_revenues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('phase_id', sa.Integer(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('revenue_date', sa.Date(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('reference_type', sa.String(length=50), nullable=True),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('recorded_by', sa.Integer(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['phase_id'], ['project_phases.id'], ),
        sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_revenues_revenue_date'), 'project_revenues', ['revenue_date'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_project_revenues_revenue_date'), table_name='project_revenues')
    op.drop_table('project_revenues')
    
    op.drop_index(op.f('ix_project_costs_cost_date'), table_name='project_costs')
    op.drop_table('project_costs')
    
    op.drop_table('project_phases')
    
    op.drop_index(op.f('ix_projects_start_date'), table_name='projects')
    op.drop_index(op.f('ix_projects_status'), table_name='projects')
    op.drop_table('projects')
    
    op.drop_index(op.f('ix_cost_center_allocations_allocation_date'), table_name='cost_center_allocations')
    op.drop_table('cost_center_allocations')
    
    op.drop_index(op.f('ix_cost_centers_is_active'), table_name='cost_centers')
    op.drop_table('cost_centers')
    
    op.drop_index(op.f('ix_bank_reconciliations_status'), table_name='bank_reconciliations')
    op.drop_table('bank_reconciliations')
    
    op.drop_index(op.f('ix_bank_transactions_matched'), table_name='bank_transactions')
    op.drop_index(op.f('ix_bank_transactions_transaction_date'), table_name='bank_transactions')
    op.drop_table('bank_transactions')
    
    op.drop_index(op.f('ix_bank_statements_statement_date'), table_name='bank_statements')
    op.drop_table('bank_statements')
    
    op.drop_index(op.f('ix_bank_accounts_gl_account_code'), table_name='bank_accounts')
    op.drop_index(op.f('ix_bank_accounts_is_active'), table_name='bank_accounts')
    op.drop_index(op.f('ix_bank_accounts_currency'), table_name='bank_accounts')
    op.drop_table('bank_accounts')
