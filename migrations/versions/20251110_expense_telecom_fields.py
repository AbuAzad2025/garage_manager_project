"""add telecom details columns to expenses

Revision ID: 20251110_expense_telecom_fields
Revises: 20251110_payment_split_currency
Create Date: 2025-11-10 22:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20251110_expense_telecom_fields"
down_revision = "20251110_payment_split_currency"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns("expenses")}

    if "telecom_phone_number" not in existing_cols:
        op.add_column(
            "expenses",
            sa.Column("telecom_phone_number", sa.String(length=30), nullable=True),
        )
    if "telecom_service_type" not in existing_cols:
        op.add_column(
            "expenses",
            sa.Column("telecom_service_type", sa.String(length=20), nullable=True),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("expenses")}
    if "ix_expenses_telecom_service_type" not in existing_indexes:
        op.create_index(
            "ix_expenses_telecom_service_type",
            "expenses",
            ["telecom_service_type"],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns("expenses")}

    if "telecom_phone_number" in existing_cols:
        op.drop_column("expenses", "telecom_phone_number")
    if "telecom_service_type" in existing_cols:
        op.drop_column("expenses", "telecom_service_type")

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("expenses")}
    if "ix_expenses_telecom_service_type" in existing_indexes:
        op.drop_index("ix_expenses_telecom_service_type", table_name="expenses")

