"""add deliverer name column to payments

Revision ID: 20251112_payment_deliverer_name
Revises: 20251111_expense_extended_fields
Create Date: 2025-11-12 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20251112_payment_deliverer_name"
down_revision = "9e5608f9b2b0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("payments")}
    if "deliverer_name" not in columns:
        op.add_column("payments", sa.Column("deliverer_name", sa.String(length=200)))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("payments")}
    if "deliverer_name" in columns:
        op.drop_column("payments", "deliverer_name")
