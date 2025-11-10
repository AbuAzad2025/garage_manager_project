"""cost centers and engineering enhancement

Revision ID: 20250104_cc_eng
Revises: 20250104_pmp_tables
Create Date: 2025-11-04 15:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = '20250104_cc_eng'
down_revision = '20250104_pmp_tables'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    def _create_if_missing(table_name, creator):
        if table_name not in existing_tables:
            creator()

    _create_if_missing('cost_center_alerts', lambda: op.create_table(
        'cost_center_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cost_center_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=15), nullable=False),
        sa.Column('threshold_type', sa.String(length=10), nullable=False),
        sa.Column('threshold_value', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('notify_manager', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('notify_emails', sa.JSON(), nullable=True),
        sa.Column('notify_users', sa.JSON(), nullable=True),
        sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
        sa.Column('trigger_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    ))

    _create_if_missing('engineering_jobs', lambda: op.create_table(
        'engineering_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_number', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.String(length=10), nullable=False),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('supervisor_id', sa.Integer(), nullable=True),
        sa.Column('cost_center_id', sa.Integer(), nullable=True),
        sa.Column('planned_start', sa.Date(), nullable=True),
        sa.Column('planned_end', sa.Date(), nullable=True),
        sa.Column('actual_start', sa.Date(), nullable=True),
        sa.Column('actual_end', sa.Date(), nullable=True),
        sa.Column('estimated_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('actual_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['employees.id']),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['supervisor_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_number')
    ))

    _create_if_missing('engineering_job_tasks', lambda: op.create_table(
        'engineering_job_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('task_number', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.String(length=10), nullable=False),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('planned_start', sa.Date(), nullable=True),
        sa.Column('planned_end', sa.Date(), nullable=True),
        sa.Column('actual_start', sa.Date(), nullable=True),
        sa.Column('actual_end', sa.Date(), nullable=True),
        sa.Column('estimated_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('actual_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['employees.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['job_id'], ['engineering_jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'task_number', name='uq_eng_task_job')
    ))

    _create_if_missing('engineering_job_documents', lambda: op.create_table(
        'engineering_job_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('document_type', sa.String(length=30), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['engineering_jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['engineering_job_tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    ))

    _create_if_missing('engineering_job_shifts', lambda: op.create_table(
        'engineering_job_shifts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('shift_date', sa.Date(), nullable=False),
        sa.Column('shift_number', sa.String(length=20), nullable=False),
        sa.Column('team_lead_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['engineering_jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_lead_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'shift_date', 'shift_number', name='uq_eng_shift_unique')
    ))

    _create_if_missing('engineering_job_shift_participants', lambda: op.create_table(
        'engineering_job_shift_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shift_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=True),
        sa.Column('hours_worked', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['shift_id'], ['engineering_job_shifts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    ))

    _create_if_missing('engineering_job_logbook', lambda: op.create_table(
        'engineering_job_logbook',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('shift_id', sa.Integer(), nullable=True),
        sa.Column('entry_time', sa.DateTime(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('entry_type', sa.String(length=30), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('actions_taken', sa.Text(), nullable=True),
        sa.Column('attachments', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['users.id']),
        sa.ForeignKeyConstraint(['job_id'], ['engineering_jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shift_id'], ['engineering_job_shifts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['engineering_job_tasks.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    ))

    return


def downgrade():
    pass


