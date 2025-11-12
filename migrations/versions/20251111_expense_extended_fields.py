"""extend expense detail fields for multiple types

Revision ID: 20251111_expense_extended_fields
Revises: 20251110_expense_telecom_fields
Create Date: 2025-11-11 20:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20251111_expense_extended_fields"
down_revision = "20251110_expense_telecom_fields"
branch_labels = None
depends_on = None


def _add_column_if_missing(inspector, table, name, column):
    if name not in {col["name"] for col in inspector.get_columns(table)}:
        op.add_column(table, column)


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    table = "expenses"

    _add_column_if_missing(inspector, table, "insurance_company_name", sa.Column("insurance_company_name", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "insurance_company_address", sa.Column("insurance_company_address", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "insurance_company_phone", sa.Column("insurance_company_phone", sa.String(length=30)))
    _add_column_if_missing(inspector, table, "marketing_company_name", sa.Column("marketing_company_name", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "marketing_company_address", sa.Column("marketing_company_address", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "marketing_coverage_details", sa.Column("marketing_coverage_details", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "bank_fee_bank_name", sa.Column("bank_fee_bank_name", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "bank_fee_notes", sa.Column("bank_fee_notes", sa.Text()))
    _add_column_if_missing(inspector, table, "gov_fee_entity_name", sa.Column("gov_fee_entity_name", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "gov_fee_entity_address", sa.Column("gov_fee_entity_address", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "gov_fee_notes", sa.Column("gov_fee_notes", sa.Text()))
    _add_column_if_missing(inspector, table, "port_fee_port_name", sa.Column("port_fee_port_name", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "port_fee_notes", sa.Column("port_fee_notes", sa.Text()))
    _add_column_if_missing(inspector, table, "travel_destination", sa.Column("travel_destination", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "travel_reason", sa.Column("travel_reason", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "travel_notes", sa.Column("travel_notes", sa.Text()))
    _add_column_if_missing(inspector, table, "shipping_company_name", sa.Column("shipping_company_name", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "shipping_notes", sa.Column("shipping_notes", sa.Text()))
    _add_column_if_missing(inspector, table, "maintenance_provider_name", sa.Column("maintenance_provider_name", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "maintenance_provider_address", sa.Column("maintenance_provider_address", sa.String(length=200)))
    _add_column_if_missing(inspector, table, "maintenance_notes", sa.Column("maintenance_notes", sa.Text()))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    table = "expenses"
    existing_cols = {col["name"] for col in inspector.get_columns(table)}

    for name in [
        "insurance_company_name",
        "insurance_company_address",
        "insurance_company_phone",
        "marketing_company_name",
        "marketing_company_address",
        "marketing_coverage_details",
        "bank_fee_bank_name",
        "bank_fee_notes",
        "gov_fee_entity_name",
        "gov_fee_entity_address",
        "gov_fee_notes",
        "port_fee_port_name",
        "port_fee_notes",
        "travel_destination",
        "travel_reason",
        "travel_notes",
        "shipping_company_name",
        "shipping_notes",
        "maintenance_provider_name",
        "maintenance_provider_address",
        "maintenance_notes",
    ]:
        if name in existing_cols:
            op.drop_column(table, name)

