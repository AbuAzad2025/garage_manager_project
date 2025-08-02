"""Add customer fields (name, phone, email) to ServiceRequest

Revision ID: 48166b6e9491
Revises: 2c240baf4438
Create Date: 2025-07-30 21:49:48.521964
"""
from alembic import op
import sqlalchemy as sa

revision = "48166b6e9491"
down_revision = "2c240baf4438"
branch_labels = None
depends_on = None

FK_NAME = "fk_audit_logs_customer_id"

def upgrade():
    """Apply migration safely on SQLite: add customer contact fields and FK."""

    # 1) Ensure FK from audit_logs.customer_id → customers.id
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.create_foreign_key(FK_NAME, "customers", ["customer_id"], ["id"])

    # 2) Add columns to service_requests
    with op.batch_alter_table("service_requests") as batch_op:
        batch_op.add_column(sa.Column("name", sa.String(100)))
        batch_op.add_column(sa.Column("phone", sa.String(20)))
        batch_op.add_column(sa.Column("email", sa.String(100)))


def downgrade():
    """Revert the migration cleanly."""

    # Drop the added columns
    with op.batch_alter_table("service_requests") as batch_op:
        batch_op.drop_column("email")
        batch_op.drop_column("phone")
        batch_op.drop_column("name")

    # Remove the FK in audit_logs
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_constraint(FK_NAME, type_="foreignkey")
