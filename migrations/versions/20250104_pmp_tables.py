"""Add PMP Advanced Tables

Revision ID: 20250104_pmp_tables
Revises: 20250103_supplier_hybrid
Create Date: 2025-11-04 02:28:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = '20250104_pmp_tables'
down_revision = '20250103_supplier_hybrid'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    def _create_table(name, definition_callable):
        if name not in existing_tables:
            definition_callable()

    _create_table('project_tasks', lambda: op.create_table(
        'project_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('phase_id', sa.Integer(), nullable=True),
        sa.Column('task_number', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('priority', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=15), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('completed_date', sa.Date(), nullable=True),
        sa.Column('estimated_hours', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('actual_hours', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('completion_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('depends_on', sa.JSON(), nullable=True),
        sa.Column('blocked_reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['phase_id'], ['project_phases.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    ))
    
    _create_table('project_resources', lambda: op.create_table(
        'project_resources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('resource_type', sa.String(length=20), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('resource_name', sa.String(length=200), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('unit_cost', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('total_cost', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('allocation_date', sa.Date(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('hours_allocated', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('hours_used', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('status', sa.String(length=15), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['project_tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    ))
    
    _create_table('project_milestones', lambda: op.create_table(
        'project_milestones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('phase_id', sa.Integer(), nullable=True),
        sa.Column('milestone_number', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('completed_date', sa.Date(), nullable=True),
        sa.Column('billing_amount', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('billing_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.Column('payment_terms_days', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=15), nullable=False),
        sa.Column('completion_criteria', sa.Text(), nullable=True),
        sa.Column('deliverables', sa.JSON(), nullable=True),
        sa.Column('approval_required', sa.Boolean(), nullable=True),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
        sa.ForeignKeyConstraint(['phase_id'], ['project_phases.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    ))
    
    _create_table('project_risks', lambda: op.create_table(
        'project_risks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('risk_number', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=15), nullable=False),
        sa.Column('probability', sa.String(length=15), nullable=False),
        sa.Column('impact', sa.String(length=15), nullable=False),
        sa.Column('risk_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('status', sa.String(length=15), nullable=False),
        sa.Column('mitigation_plan', sa.Text(), nullable=True),
        sa.Column('contingency_plan', sa.Text(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('identified_date', sa.Date(), nullable=False),
        sa.Column('review_date', sa.Date(), nullable=True),
        sa.Column('closed_date', sa.Date(), nullable=True),
        sa.Column('actual_impact_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    ))
    
    _create_table('project_change_orders', lambda: op.create_table(
        'project_change_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('change_number', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('requested_by', sa.Integer(), nullable=True),
        sa.Column('requested_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('scope_change', sa.Text(), nullable=True),
        sa.Column('cost_impact', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('schedule_impact_days', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_date', sa.Date(), nullable=True),
        sa.Column('implemented_date', sa.Date(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('change_number')
    ))
    
    _create_table('project_issues', lambda: op.create_table(
        'project_issues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('issue_number', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=15), nullable=False),
        sa.Column('severity', sa.String(length=15), nullable=False),
        sa.Column('priority', sa.String(length=15), nullable=False),
        sa.Column('status', sa.String(length=15), nullable=False),
        sa.Column('reported_by', sa.Integer(), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('reported_date', sa.Date(), nullable=False),
        sa.Column('resolved_date', sa.Date(), nullable=True),
        sa.Column('resolution', sa.Text(), nullable=True),
        sa.Column('cost_impact', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('schedule_impact_days', sa.Integer(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('preventive_action', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reported_by'], ['users.id']),
        sa.ForeignKeyConstraint(['task_id'], ['project_tasks.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    ))
    
    _create_table('resource_time_logs', lambda: op.create_table(
        'resource_time_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('log_date', sa.Date(), nullable=False),
        sa.Column('hours_worked', sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column('hourly_rate', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('total_cost', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('approved', sa.Boolean(), nullable=True),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resource_id'], ['project_resources.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['project_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    ))

    return


def downgrade():
    pass

