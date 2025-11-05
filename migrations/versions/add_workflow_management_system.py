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
    op.create_table('workflow_definitions',
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
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workflow_code')
    )
    op.create_index('ix_workflow_def_entity_active', 'workflow_definitions', ['entity_type', 'is_active'], unique=False)
    op.create_index(op.f('ix_workflow_definitions_created_by'), 'workflow_definitions', ['created_by'], unique=False)
    op.create_index(op.f('ix_workflow_definitions_entity_type'), 'workflow_definitions', ['entity_type'], unique=False)
    op.create_index(op.f('ix_workflow_definitions_is_active'), 'workflow_definitions', ['is_active'], unique=False)
    op.create_index(op.f('ix_workflow_definitions_updated_by'), 'workflow_definitions', ['updated_by'], unique=False)
    op.create_index(op.f('ix_workflow_definitions_workflow_code'), 'workflow_definitions', ['workflow_code'], unique=False)
    op.create_index(op.f('ix_workflow_definitions_workflow_type'), 'workflow_definitions', ['workflow_type'], unique=False)
    
    op.create_table('workflow_instances',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('workflow_definition_id', sa.Integer(), nullable=False),
    sa.Column('instance_code', sa.String(length=50), nullable=False),
    sa.Column('entity_type', sa.String(length=50), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('current_step', sa.Integer(), nullable=False),
    sa.Column('total_steps', sa.Integer(), nullable=False),
    sa.Column('started_by', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('completed_by', sa.Integer(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(), nullable=True),
    sa.Column('cancelled_by', sa.Integer(), nullable=True),
    sa.Column('cancellation_reason', sa.Text(), nullable=True),
    sa.Column('due_date', sa.DateTime(), nullable=True),
    sa.Column('context_data', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['cancelled_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['completed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['started_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workflow_definition_id'], ['workflow_definitions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('instance_code')
    )
    op.create_index('ix_workflow_inst_entity', 'workflow_instances', ['entity_type', 'entity_id'], unique=False)
    op.create_index('ix_workflow_inst_status_date', 'workflow_instances', ['status', 'started_at'], unique=False)
    op.create_index(op.f('ix_workflow_instances_cancelled_at'), 'workflow_instances', ['cancelled_at'], unique=False)
    op.create_index(op.f('ix_workflow_instances_cancelled_by'), 'workflow_instances', ['cancelled_by'], unique=False)
    op.create_index(op.f('ix_workflow_instances_completed_at'), 'workflow_instances', ['completed_at'], unique=False)
    op.create_index(op.f('ix_workflow_instances_completed_by'), 'workflow_instances', ['completed_by'], unique=False)
    op.create_index(op.f('ix_workflow_instances_due_date'), 'workflow_instances', ['due_date'], unique=False)
    op.create_index(op.f('ix_workflow_instances_entity_id'), 'workflow_instances', ['entity_id'], unique=False)
    op.create_index(op.f('ix_workflow_instances_entity_type'), 'workflow_instances', ['entity_type'], unique=False)
    op.create_index(op.f('ix_workflow_instances_instance_code'), 'workflow_instances', ['instance_code'], unique=False)
    op.create_index(op.f('ix_workflow_instances_started_at'), 'workflow_instances', ['started_at'], unique=False)
    op.create_index(op.f('ix_workflow_instances_started_by'), 'workflow_instances', ['started_by'], unique=False)
    op.create_index(op.f('ix_workflow_instances_status'), 'workflow_instances', ['status'], unique=False)
    op.create_index(op.f('ix_workflow_instances_workflow_definition_id'), 'workflow_instances', ['workflow_definition_id'], unique=False)
    
    op.create_table('workflow_actions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('workflow_instance_id', sa.Integer(), nullable=False),
    sa.Column('step_number', sa.Integer(), nullable=False),
    sa.Column('step_name', sa.String(length=200), nullable=False),
    sa.Column('action_type', sa.String(length=20), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('action_date', sa.DateTime(), nullable=False),
    sa.Column('decision', sa.String(length=50), nullable=True),
    sa.Column('comments', sa.Text(), nullable=True),
    sa.Column('attachments', sa.JSON(), nullable=True),
    sa.Column('delegated_to', sa.Integer(), nullable=True),
    sa.Column('delegated_at', sa.DateTime(), nullable=True),
    sa.Column('duration_hours', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['delegated_to'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workflow_instance_id'], ['workflow_instances.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_workflow_action_actor_date', 'workflow_actions', ['actor_id', 'action_date'], unique=False)
    op.create_index('ix_workflow_action_instance_step', 'workflow_actions', ['workflow_instance_id', 'step_number'], unique=False)
    op.create_index(op.f('ix_workflow_actions_action_date'), 'workflow_actions', ['action_date'], unique=False)
    op.create_index(op.f('ix_workflow_actions_action_type'), 'workflow_actions', ['action_type'], unique=False)
    op.create_index(op.f('ix_workflow_actions_actor_id'), 'workflow_actions', ['actor_id'], unique=False)
    op.create_index(op.f('ix_workflow_actions_delegated_to'), 'workflow_actions', ['delegated_to'], unique=False)
    op.create_index(op.f('ix_workflow_actions_workflow_instance_id'), 'workflow_actions', ['workflow_instance_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_workflow_actions_workflow_instance_id'), table_name='workflow_actions')
    op.drop_index(op.f('ix_workflow_actions_delegated_to'), table_name='workflow_actions')
    op.drop_index(op.f('ix_workflow_actions_actor_id'), table_name='workflow_actions')
    op.drop_index(op.f('ix_workflow_actions_action_type'), table_name='workflow_actions')
    op.drop_index(op.f('ix_workflow_actions_action_date'), table_name='workflow_actions')
    op.drop_index('ix_workflow_action_instance_step', table_name='workflow_actions')
    op.drop_index('ix_workflow_action_actor_date', table_name='workflow_actions')
    op.drop_table('workflow_actions')
    
    op.drop_index(op.f('ix_workflow_instances_workflow_definition_id'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_status'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_started_by'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_started_at'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_instance_code'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_entity_type'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_entity_id'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_due_date'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_completed_by'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_completed_at'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_cancelled_by'), table_name='workflow_instances')
    op.drop_index(op.f('ix_workflow_instances_cancelled_at'), table_name='workflow_instances')
    op.drop_index('ix_workflow_inst_status_date', table_name='workflow_instances')
    op.drop_index('ix_workflow_inst_entity', table_name='workflow_instances')
    op.drop_table('workflow_instances')
    
    op.drop_index(op.f('ix_workflow_definitions_workflow_type'), table_name='workflow_definitions')
    op.drop_index(op.f('ix_workflow_definitions_workflow_code'), table_name='workflow_definitions')
    op.drop_index(op.f('ix_workflow_definitions_updated_by'), table_name='workflow_definitions')
    op.drop_index(op.f('ix_workflow_definitions_is_active'), table_name='workflow_definitions')
    op.drop_index(op.f('ix_workflow_definitions_entity_type'), table_name='workflow_definitions')
    op.drop_index(op.f('ix_workflow_definitions_created_by'), table_name='workflow_definitions')
    op.drop_index('ix_workflow_def_entity_active', table_name='workflow_definitions')
    op.drop_table('workflow_definitions')

