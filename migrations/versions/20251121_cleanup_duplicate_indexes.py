"""cleanup duplicate indexes

Revision ID: 20251121_cleanup_duplicate_indexes
Revises: 20251119_check_permission_fields
Create Date: 2025-11-21 11:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "20251121_cleanup_duplicate_indexes"
down_revision = "20251119_check_permission_fields"
branch_labels = None
depends_on = None


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)


def upgrade():
    targets = [
        ("exchange_transactions", "ix_exchange_supplier"),
        ("sale_lines", "ix_sale_line_sale"),
        ("payments", "ix_payments_status"),
        ("payments", "ix_payments_refund_of_id"),
        ("payments", "ix_payments_direction"),
        ("payments", "ix_payments_payment_date"),
        ("service_parts", "ix_service_part_partner"),
        ("service_tasks", "ix_service_task_service"),
        ("project_risks", "ix_risk_score"),
        ("cost_allocation_rules", "ix_allocation_rule_active"),
        ("cost_allocation_lines", "ix_allocation_line_rule"),
        ("cost_allocation_executions", "ix_allocation_exec_date"),
        ("engineering_teams", "ix_eng_team_specialty"),
        ("engineering_teams", "ix_eng_team_active"),
        ("engineering_skills", "ix_skill_category"),
        ("employee_skills", "ix_employee_skill_expiry"),
        ("engineering_tasks", "ix_eng_task_priority"),
        ("engineering_tasks", "ix_eng_task_status"),
        ("engineering_timesheets", "ix_timesheet_status"),
        ("engineering_timesheets", "ix_timesheet_task"),
    ]
    for table_name, index_name in targets:
        _drop_index_if_exists(table_name, index_name)


def downgrade():
    # Downgrade is intentionally left empty: the dropped indexes were duplicates.
    pass

