"""add_workflow_management_system

Revision ID: workflow_bpm_001
Revises: 
Create Date: 2025-01-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = 'workflow_bpm_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    def _create_if_missing(name, creator):
        if name not in existing_tables:
            creator()

    _create_if_missing('workflow_definitions', lambda: op.create_table(
        'workflow_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_code', sa.String(length=50), nullable=False),
        sa.Column('workflow_name', sa.String(length=200), nullable=False),
        sa.Column('workflow_name_ar', sa.String(length=200), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('workflow_type', sa.String(length=20), nullable=False),
        sa.Column('entity_type', sa.String(length=20), nullable=False),
        sa.Column('steps_definition', sa.JSON(), nullable=False),
        sa.Column('auto_start', sa.Boolean(), nullable=False),
        sa.Column('auto_start_condition', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('timeout_hours', sa.Integer(), nullable=True),
        sa.Column('escalation_rules', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workflow_code')
    ))

    _create_if_missing('workflow_instances', lambda: op.create_table(
        'workflow_instances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('entity_reference', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('current_step', sa.String(length=50), nullable=True),
        sa.Column('assignees', sa.JSON(), nullable=True),
        sa.Column('started_by', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.Column('archived_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['archived_by'], ['users.id']),
        sa.ForeignKeyConstraint(['started_by'], ['users.id']),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow_definitions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    ))

    _create_if_missing('workflow_steps', lambda: op.create_table(
        'workflow_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('step_code', sa.String(length=50), nullable=False),
        sa.Column('step_name', sa.String(length=200), nullable=False),
        sa.Column('step_name_ar', sa.String(length=200), nullable=True),
        sa.Column('sequencer', sa.Integer(), nullable=False),
        sa.Column('step_type', sa.String(length=20), nullable=False),
        sa.Column('assignee_type', sa.String(length=20), nullable=False),
        sa.Column('assignee_roles', sa.JSON(), nullable=True),
        sa.Column('assignee_users', sa.JSON(), nullable=True),
        sa.Column('approval_rules', sa.JSON(), nullable=True),
        sa.Column('sla_hours', sa.Integer(), nullable=True),
        sa.Column('escalation_to', sa.JSON(), nullable=True),
        sa.Column('is_auto_assign', sa.Boolean(), nullable=False),
        sa.Column('auto_assign_condition', sa.JSON(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow_definitions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workflow_id', 'step_code')
    ))

    _create_if_missing('workflow_step_instances', lambda: op.create_table(
        'workflow_step_instances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instance_id', sa.Integer(), nullable=False),
        sa.Column('step_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('assignees', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('decision', sa.String(length=20), nullable=True),
        sa.Column('decision_by', sa.Integer(), nullable=True),
        sa.Column('decision_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['decision_by'], ['users.id']),
        sa.ForeignKeyConstraint(['instance_id'], ['workflow_instances.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['step_id'], ['workflow_steps.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    ))

    _create_if_missing('workflow_transitions', lambda: op.create_table(
        'workflow_transitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('from_step_id', sa.Integer(), nullable=True),
        sa.Column('to_step_id', sa.Integer(), nullable=True),
        sa.Column('trigger', sa.String(length=50), nullable=False),
        sa.Column('condition', sa.JSON(), nullable=True),
        sa.Column('auto_transition', sa.Boolean(), nullable=False),
        sa.Column('auto_condition', sa.JSON(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['from_step_id'], ['workflow_steps.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['to_step_id'], ['workflow_steps.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow_definitions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    ))

    _create_if_missing('workflow_notifications', lambda: op.create_table(
        'workflow_notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('step_id', sa.Integer(), nullable=True),
        sa.Column('notification_type', sa.String(length=20), nullable=False),
        sa.Column('recipients', sa.JSON(), nullable=False),
        sa.Column('subject', sa.String(length=200), nullable=False),
        sa.Column('subject_ar', sa.String(length=200), nullable=True),
        sa.Column('message_template', sa.Text(), nullable=False),
        sa.Column('message_template_ar', sa.Text(), nullable=True),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('send_condition', sa.JSON(), nullable=True),
        sa.Column('delay_minutes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['step_id'], ['workflow_steps.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow_definitions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    ))

    return


def downgrade():
    pass

