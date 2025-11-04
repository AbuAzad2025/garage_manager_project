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
    
    op.create_table('cost_center_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cost_center_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.Enum('BUDGET_EXCEEDED', 'BUDGET_WARNING', 'NO_ACTIVITY', 'UNUSUAL_SPIKE', name='cc_alert_type'), nullable=False),
        sa.Column('threshold_type', sa.Enum('PERCENTAGE', 'AMOUNT', name='cc_threshold_type'), nullable=False),
        sa.Column('threshold_value', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('notify_manager', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('notify_emails', sa.JSON(), nullable=True),
        sa.Column('notify_users', sa.JSON(), nullable=True),
        sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
        sa.Column('trigger_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cc_alert_center_active', 'cost_center_alerts', ['cost_center_id', 'is_active'])
    
    op.create_table('cost_center_alert_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alert_id', sa.Integer(), nullable=True),
        sa.Column('cost_center_id', sa.Integer(), nullable=True),
        sa.Column('triggered_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('trigger_value', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('threshold_value', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('severity', sa.Enum('INFO', 'WARNING', 'CRITICAL', name='cc_alert_severity'), nullable=True),
        sa.Column('notified_users', sa.JSON(), nullable=True),
        sa.Column('notification_sent', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['alert_id'], ['cost_center_alerts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cc_alert_log_date', 'cost_center_alert_logs', ['triggered_at'])
    
    op.create_table('cost_allocation_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_cost_center_id', sa.Integer(), nullable=True),
        sa.Column('allocation_method', sa.Enum('PERCENTAGE', 'RATIO', 'EQUAL', 'EMPLOYEE_COUNT', 'REVENUE_BASED', 'AREA_BASED', 'CUSTOM', name='allocation_method'), nullable=False),
        sa.Column('frequency', sa.Enum('MANUAL', 'DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY', name='allocation_frequency'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('auto_execute', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_executed_at', sa.DateTime(), nullable=True),
        sa.Column('next_execution_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['source_cost_center_id'], ['cost_centers.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_allocation_rule_code')
    )
    op.create_index('ix_allocation_rule_active', 'cost_allocation_rules', ['is_active'])
    
    op.create_table('cost_allocation_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('target_cost_center_id', sa.Integer(), nullable=False),
        sa.Column('percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('fixed_amount', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('allocation_driver', sa.String(length=100), nullable=True),
        sa.Column('driver_value', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['rule_id'], ['cost_allocation_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_cost_center_id'], ['cost_centers.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('percentage >= 0 AND percentage <= 100', name='ck_allocation_line_percentage')
    )
    op.create_index('ix_allocation_line_rule', 'cost_allocation_lines', ['rule_id'])
    
    op.create_table('cost_allocation_executions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=True),
        sa.Column('execution_date', sa.Date(), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('status', sa.Enum('DRAFT', 'EXECUTED', 'REVERSED', name='allocation_exec_status'), nullable=False, server_default='DRAFT'),
        sa.Column('gl_batch_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['rule_id'], ['cost_allocation_rules.id'], ),
        sa.ForeignKeyConstraint(['gl_batch_id'], ['gl_batches.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_allocation_exec_date', 'cost_allocation_executions', ['execution_date'])
    
    op.create_table('cost_allocation_execution_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('execution_id', sa.Integer(), nullable=False),
        sa.Column('source_cost_center_id', sa.Integer(), nullable=True),
        sa.Column('target_cost_center_id', sa.Integer(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('gl_batch_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['execution_id'], ['cost_allocation_executions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_cost_center_id'], ['cost_centers.id'], ),
        sa.ForeignKeyConstraint(['target_cost_center_id'], ['cost_centers.id'], ),
        sa.ForeignKeyConstraint(['gl_batch_id'], ['gl_batches.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('engineering_teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('team_leader_id', sa.Integer(), nullable=True),
        sa.Column('specialty', sa.Enum('MECHANICAL', 'ELECTRICAL', 'CIVIL', 'AUTOMOTIVE', 'SOFTWARE', 'MAINTENANCE', 'HVAC', 'PLUMBING', 'GENERAL', name='eng_specialty'), nullable=False),
        sa.Column('cost_center_id', sa.Integer(), nullable=True),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('max_concurrent_tasks', sa.Integer(), nullable=False, server_default=sa.text('5')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('equipment_inventory', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['team_leader_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id'], ),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_eng_team_code')
    )
    op.create_index('ix_eng_team_active', 'engineering_teams', ['is_active'])
    op.create_index('ix_eng_team_specialty', 'engineering_teams', ['specialty'])
    
    op.create_table('engineering_team_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.Enum('LEADER', 'SENIOR', 'ENGINEER', 'JUNIOR', 'TECHNICIAN', 'APPRENTICE', name='team_member_role'), nullable=False),
        sa.Column('join_date', sa.Date(), nullable=False),
        sa.Column('leave_date', sa.Date(), nullable=True),
        sa.Column('hourly_rate', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['team_id'], ['engineering_teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'employee_id', name='uq_team_member')
    )
    op.create_index('ix_team_member_active', 'engineering_team_members', ['is_active'])
    
    op.create_table('engineering_skills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('name_ar', sa.String(length=200), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_certification_required', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('certification_validity_months', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_eng_skill_code')
    )
    op.create_index('ix_skill_category', 'engineering_skills', ['category'])
    
    op.create_table('employee_skills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('proficiency_level', sa.Enum('BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'EXPERT', name='proficiency_level'), nullable=False),
        sa.Column('years_experience', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('certification_number', sa.String(length=100), nullable=True),
        sa.Column('certification_authority', sa.String(length=200), nullable=True),
        sa.Column('certification_date', sa.Date(), nullable=True),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('verified_by', sa.Integer(), nullable=True),
        sa.Column('verification_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['engineering_skills.id'], ),
        sa.ForeignKeyConstraint(['verified_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'skill_id', name='uq_employee_skill')
    )
    op.create_index('ix_employee_skill_expiry', 'employee_skills', ['expiry_date'])
    
    op.create_table('engineering_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_number', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('task_type', sa.Enum('DESIGN', 'INSPECTION', 'MAINTENANCE', 'INSTALLATION', 'REPAIR', 'CONSULTATION', 'TESTING', 'CALIBRATION', 'TRAINING', 'OTHER', name='eng_task_type'), nullable=False),
        sa.Column('priority', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'URGENT', 'CRITICAL', name='eng_task_priority'), nullable=False, server_default='MEDIUM'),
        sa.Column('status', sa.Enum('PENDING', 'ASSIGNED', 'IN_PROGRESS', 'ON_HOLD', 'REVIEW', 'COMPLETED', 'CANCELLED', 'DEFERRED', name='eng_task_status'), nullable=False, server_default='PENDING'),
        sa.Column('assigned_team_id', sa.Integer(), nullable=True),
        sa.Column('assigned_to_id', sa.Integer(), nullable=True),
        sa.Column('required_skills', sa.JSON(), nullable=True),
        sa.Column('estimated_hours', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('actual_hours', sa.Numeric(precision=8, scale=2), nullable=False, server_default=sa.text('0')),
        sa.Column('estimated_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('actual_cost', sa.Numeric(precision=15, scale=2), nullable=False, server_default=sa.text('0')),
        sa.Column('scheduled_start', sa.DateTime(), nullable=True),
        sa.Column('scheduled_end', sa.DateTime(), nullable=True),
        sa.Column('actual_start', sa.DateTime(), nullable=True),
        sa.Column('actual_end', sa.DateTime(), nullable=True),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('location', sa.String(length=300), nullable=True),
        sa.Column('equipment_needed', sa.Text(), nullable=True),
        sa.Column('tools_needed', sa.Text(), nullable=True),
        sa.Column('materials_needed', sa.JSON(), nullable=True),
        sa.Column('safety_requirements', sa.Text(), nullable=True),
        sa.Column('quality_standards', sa.Text(), nullable=True),
        sa.Column('completion_notes', sa.Text(), nullable=True),
        sa.Column('completion_photos', sa.JSON(), nullable=True),
        sa.Column('customer_satisfaction_rating', sa.Integer(), nullable=True),
        sa.Column('customer_feedback', sa.Text(), nullable=True),
        sa.Column('cost_center_id', sa.Integer(), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('service_request_id', sa.Integer(), nullable=True),
        sa.Column('parent_task_id', sa.Integer(), nullable=True),
        sa.Column('gl_batch_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_team_id'], ['engineering_teams.id'], ),
        sa.ForeignKeyConstraint(['assigned_to_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['service_request_id'], ['service_requests.id'], ),
        sa.ForeignKeyConstraint(['parent_task_id'], ['engineering_tasks.id'], ),
        sa.ForeignKeyConstraint(['gl_batch_id'], ['gl_batches.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_number', name='uq_eng_task_number'),
        sa.CheckConstraint('customer_satisfaction_rating >= 1 AND customer_satisfaction_rating <= 5', name='ck_task_rating_range')
    )
    op.create_index('ix_eng_task_status', 'engineering_tasks', ['status'])
    op.create_index('ix_eng_task_priority', 'engineering_tasks', ['priority'])
    op.create_index('ix_eng_task_assigned', 'engineering_tasks', ['assigned_to_id', 'status'])
    op.create_index('ix_eng_task_scheduled', 'engineering_tasks', ['scheduled_start', 'scheduled_end'])
    
    op.create_table('engineering_timesheets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('break_duration_minutes', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('actual_work_hours', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('billable_hours', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('hourly_rate', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('total_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('productivity_rating', sa.Enum('POOR', 'FAIR', 'GOOD', 'VERY_GOOD', 'EXCELLENT', name='productivity_rating'), nullable=True),
        sa.Column('work_description', sa.Text(), nullable=True),
        sa.Column('issues_encountered', sa.Text(), nullable=True),
        sa.Column('materials_used', sa.JSON(), nullable=True),
        sa.Column('location', sa.String(length=300), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', name='timesheet_status'), nullable=False, server_default='DRAFT'),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approval_date', sa.DateTime(), nullable=True),
        sa.Column('approval_notes', sa.Text(), nullable=True),
        sa.Column('cost_center_id', sa.Integer(), nullable=True),
        sa.Column('gl_batch_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['engineering_tasks.id'], ),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['cost_center_id'], ['cost_centers.id'], ),
        sa.ForeignKeyConstraint(['gl_batch_id'], ['gl_batches.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('actual_work_hours > 0', name='ck_timesheet_hours_positive'),
        sa.CheckConstraint('break_duration_minutes >= 0', name='ck_timesheet_break_positive')
    )
    op.create_index('ix_timesheet_employee_date', 'engineering_timesheets', ['employee_id', 'work_date'])
    op.create_index('ix_timesheet_task', 'engineering_timesheets', ['task_id'])
    op.create_index('ix_timesheet_status', 'engineering_timesheets', ['status'])


def downgrade():
    op.drop_index('ix_timesheet_status', table_name='engineering_timesheets')
    op.drop_index('ix_timesheet_task', table_name='engineering_timesheets')
    op.drop_index('ix_timesheet_employee_date', table_name='engineering_timesheets')
    op.drop_table('engineering_timesheets')
    
    op.drop_index('ix_eng_task_scheduled', table_name='engineering_tasks')
    op.drop_index('ix_eng_task_assigned', table_name='engineering_tasks')
    op.drop_index('ix_eng_task_priority', table_name='engineering_tasks')
    op.drop_index('ix_eng_task_status', table_name='engineering_tasks')
    op.drop_table('engineering_tasks')
    
    op.drop_index('ix_employee_skill_expiry', table_name='employee_skills')
    op.drop_table('employee_skills')
    
    op.drop_index('ix_skill_category', table_name='engineering_skills')
    op.drop_table('engineering_skills')
    
    op.drop_index('ix_team_member_active', table_name='engineering_team_members')
    op.drop_table('engineering_team_members')
    
    op.drop_index('ix_eng_team_specialty', table_name='engineering_teams')
    op.drop_index('ix_eng_team_active', table_name='engineering_teams')
    op.drop_table('engineering_teams')
    
    op.drop_table('cost_allocation_execution_lines')
    
    op.drop_index('ix_allocation_exec_date', table_name='cost_allocation_executions')
    op.drop_table('cost_allocation_executions')
    
    op.drop_index('ix_allocation_line_rule', table_name='cost_allocation_lines')
    op.drop_table('cost_allocation_lines')
    
    op.drop_index('ix_allocation_rule_active', table_name='cost_allocation_rules')
    op.drop_table('cost_allocation_rules')
    
    op.drop_index('ix_cc_alert_log_date', table_name='cost_center_alert_logs')
    op.drop_table('cost_center_alert_logs')
    
    op.drop_index('ix_cc_alert_center_active', table_name='cost_center_alerts')
    op.drop_table('cost_center_alerts')


