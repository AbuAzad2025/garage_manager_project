"""add budget and assets tables clean

Revision ID: 20251101_budget_assets_clean
Revises: 20251101_perf_idx
Create Date: 2025-11-01 23:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '20251101_budget_assets_clean'
down_revision = '20251101_perf_idx'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(None, schema=None) as batch_op:
        pass
    
    try:
        op.create_table('budgets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year', sa.Integer(), nullable=False),
        sa.Column('account_code', sa.String(length=20), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('site_id', sa.Integer(), nullable=True),
        sa.Column('allocated_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.Column('archived_by', sa.Integer(), nullable=True),
        sa.CheckConstraint('allocated_amount >= 0', name='ck_budget_allocated_ge_0'),
        sa.ForeignKeyConstraint(['account_code'], ['accounts.code'], name='fk_budgets_account', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], name='fk_budgets_branch', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], name='fk_budgets_site', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year', 'account_code', 'branch_id', 'site_id', name='uq_budget_year_account_branch_site')
        )
        op.create_index('ix_budget_year_account', 'budgets', ['fiscal_year', 'account_code'], unique=False)
        op.create_index('ix_budget_year_branch', 'budgets', ['fiscal_year', 'branch_id'], unique=False)
        op.create_index('ix_budgets_account_code', 'budgets', ['account_code'], unique=False)
        op.create_index('ix_budgets_branch_id', 'budgets', ['branch_id'], unique=False)
        op.create_index('ix_budgets_fiscal_year', 'budgets', ['fiscal_year'], unique=False)
        op.create_index('ix_budgets_is_active', 'budgets', ['is_active'], unique=False)
        op.create_index('ix_budgets_site_id', 'budgets', ['site_id'], unique=False)
    except:
        pass
    
    try:
        op.create_table('budget_commitments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('budget_id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.Enum('EXPENSE', 'PURCHASE', 'QUOTE', name='commitment_source_type', native_enum=False), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('committed_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('commitment_date', sa.Date(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'PAID', 'CANCELLED', name='commitment_status', native_enum=False), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('committed_amount >= 0', name='ck_commitment_amount_ge_0'),
        sa.ForeignKeyConstraint(['budget_id'], ['budgets.id'], name='fk_commitments_budget', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_type', 'source_id', name='uq_commitment_source')
        )
        op.create_index('ix_commitment_budget_status', 'budget_commitments', ['budget_id', 'status'], unique=False)
        op.create_index('ix_budget_commitments_budget_id', 'budget_commitments', ['budget_id'], unique=False)
        op.create_index('ix_budget_commitments_source_type', 'budget_commitments', ['source_type'], unique=False)
        op.create_index('ix_budget_commitments_source_id', 'budget_commitments', ['source_id'], unique=False)
        op.create_index('ix_budget_commitments_status', 'budget_commitments', ['status'], unique=False)
    except:
        pass
    
    try:
        op.create_table('fixed_asset_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('account_code', sa.String(length=20), nullable=False),
        sa.Column('depreciation_account_code', sa.String(length=20), nullable=False),
        sa.Column('useful_life_years', sa.Integer(), nullable=False),
        sa.Column('depreciation_method', sa.Enum('STRAIGHT_LINE', 'DECLINING_BALANCE', name='depreciation_method', native_enum=False), nullable=False),
        sa.Column('depreciation_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('depreciation_rate >= 0 AND depreciation_rate <= 100', name='ck_depreciation_rate_range'),
        sa.CheckConstraint('useful_life_years > 0', name='ck_useful_life_gt_0'),
        sa.ForeignKeyConstraint(['account_code'], ['accounts.code'], name='fk_asset_cat_account', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['depreciation_account_code'], ['accounts.code'], name='fk_asset_cat_dep_account', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
        )
        op.create_index('ix_fixed_asset_categories_code', 'fixed_asset_categories', ['code'], unique=False)
        op.create_index('ix_fixed_asset_categories_name', 'fixed_asset_categories', ['name'], unique=False)
        op.create_index('ix_fixed_asset_categories_is_active', 'fixed_asset_categories', ['is_active'], unique=False)
    except:
        pass
    
    try:
        op.create_table('fixed_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_number', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('site_id', sa.Integer(), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=False),
        sa.Column('purchase_price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('supplier_id', sa.Integer(), nullable=True),
        sa.Column('serial_number', sa.String(length=100), nullable=True),
        sa.Column('barcode', sa.String(length=100), nullable=True),
        sa.Column('location', sa.String(length=200), nullable=True),
        sa.Column('status', sa.Enum('ACTIVE', 'DISPOSED', 'SOLD', 'STOLEN', 'DAMAGED', name='asset_status', native_enum=False), nullable=False),
        sa.Column('disposal_date', sa.Date(), nullable=True),
        sa.Column('disposal_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('disposal_notes', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_archived', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.Column('archived_by', sa.Integer(), nullable=True),
        sa.CheckConstraint('purchase_price >= 0', name='ck_asset_price_ge_0'),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], name='fk_assets_branch', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['category_id'], ['fixed_asset_categories.id'], name='fk_assets_category', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], name='fk_assets_site', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['partners.id'], name='fk_assets_supplier'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_number')
        )
        op.create_index('ix_asset_category_branch', 'fixed_assets', ['category_id', 'branch_id'], unique=False)
        op.create_index('ix_asset_status_date', 'fixed_assets', ['status', 'purchase_date'], unique=False)
        op.create_index('ix_fixed_assets_asset_number', 'fixed_assets', ['asset_number'], unique=False)
        op.create_index('ix_fixed_assets_category_id', 'fixed_assets', ['category_id'], unique=False)
        op.create_index('ix_fixed_assets_branch_id', 'fixed_assets', ['branch_id'], unique=False)
        op.create_index('ix_fixed_assets_status', 'fixed_assets', ['status'], unique=False)
    except:
        pass
    
    try:
        op.create_table('asset_depreciations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year', sa.Integer(), nullable=False),
        sa.Column('fiscal_month', sa.Integer(), nullable=True),
        sa.Column('depreciation_date', sa.Date(), nullable=False),
        sa.Column('depreciation_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('accumulated_depreciation', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('book_value', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('gl_batch_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('depreciation_amount >= 0', name='ck_depreciation_amount_ge_0'),
        sa.CheckConstraint('fiscal_month >= 1 AND fiscal_month <= 12', name='ck_fiscal_month_range'),
        sa.ForeignKeyConstraint(['asset_id'], ['fixed_assets.id'], name='fk_depreciation_asset', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['gl_batch_id'], ['gl_batches.id'], name='fk_depreciation_gl'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'fiscal_year', 'fiscal_month', name='uq_depreciation_asset_period')
        )
        op.create_index('ix_depreciation_year_month', 'asset_depreciations', ['fiscal_year', 'fiscal_month'], unique=False)
        op.create_index('ix_asset_depreciations_asset_id', 'asset_depreciations', ['asset_id'], unique=False)
        op.create_index('ix_asset_depreciations_fiscal_year', 'asset_depreciations', ['fiscal_year'], unique=False)
    except:
        pass
    
    try:
        op.create_table('asset_maintenance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('maintenance_date', sa.Date(), nullable=False),
        sa.Column('maintenance_type', sa.String(length=100), nullable=True),
        sa.Column('cost', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('expense_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('next_maintenance_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.Column('archived_by', sa.Integer(), nullable=True),
        sa.CheckConstraint('cost >= 0', name='ck_maintenance_cost_ge_0'),
        sa.ForeignKeyConstraint(['asset_id'], ['fixed_assets.id'], name='fk_maintenance_asset', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['expense_id'], ['expenses.id'], name='fk_maintenance_expense'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_maintenance_asset_date', 'asset_maintenance', ['asset_id', 'maintenance_date'], unique=False)
        op.create_index('ix_asset_maintenance_asset_id', 'asset_maintenance', ['asset_id'], unique=False)
    except:
        pass


def downgrade():
    try:
        op.drop_table('asset_maintenance')
    except:
        pass
    
    try:
        op.drop_table('asset_depreciations')
    except:
        pass
    
    try:
        op.drop_table('fixed_assets')
    except:
        pass
    
    try:
        op.drop_table('fixed_asset_categories')
    except:
        pass
    
    try:
        op.drop_table('budget_commitments')
    except:
        pass
    
    try:
        op.drop_table('budgets')
    except:
        pass

