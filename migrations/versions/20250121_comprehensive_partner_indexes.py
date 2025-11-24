"""comprehensive partner indexes for performance

Revision ID: 20250121_partner_indexes
Revises: 20251120_partner_balance_cols
Create Date: 2025-01-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text


revision = '20250121_partner_indexes'
down_revision = '20251120_partner_balance_cols'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    
    existing_partner_indexes = {idx["name"] for idx in inspector.get_indexes("partners")}
    
    partner_indexes = [
        {
            "name": "ix_partners_is_archived_current_balance",
            "columns": ["is_archived", "current_balance"],
            "description": "Composite index for filtering archived partners and sorting by balance"
        },
        {
            "name": "ix_partners_is_archived_name",
            "columns": ["is_archived", "name"],
            "description": "Composite index for filtering archived partners and sorting by name"
        },
        {
            "name": "ix_partners_customer_id_current_balance",
            "columns": ["customer_id", "current_balance"],
            "description": "Composite index for partner-customer relationships with balance queries"
        },
        {
            "name": "ix_partners_currency_current_balance",
            "columns": ["currency", "current_balance"],
            "description": "Composite index for currency-based balance queries"
        },
        {
            "name": "ix_partners_share_percentage",
            "columns": ["share_percentage"],
            "description": "Index for share_percentage filtering"
        }
    ]
    
    if is_sqlite:
        for idx_info in partner_indexes:
            if idx_info["name"] not in existing_partner_indexes:
                columns_str = ", ".join(idx_info["columns"])
                op.execute(f'CREATE INDEX IF NOT EXISTS {idx_info["name"]} ON partners ({columns_str})')
    else:
        for idx_info in partner_indexes:
            if idx_info["name"] not in existing_partner_indexes:
                op.create_index(
                    idx_info["name"],
                    "partners",
                    idx_info["columns"],
                    unique=False
                )
    
    try:
        existing_payment_indexes = {idx["name"] for idx in inspector.get_indexes("payments")}
    except Exception:
        existing_payment_indexes = set()
    
    payment_indexes = [
        {
            "name": "ix_payments_partner_id_status",
            "columns": ["partner_id", "status"],
            "description": "Composite index for partner payments with status filtering"
        },
        {
            "name": "ix_payments_partner_id_direction",
            "columns": ["partner_id", "direction"],
            "description": "Composite index for partner payments with direction filtering"
        },
        {
            "name": "ix_payments_partner_id_date",
            "columns": ["partner_id", "payment_date"],
            "description": "Composite index for partner payments with date filtering"
        }
    ]
    
    if is_sqlite:
        for idx_info in payment_indexes:
            if idx_info["name"] not in existing_payment_indexes:
                columns_str = ", ".join(idx_info["columns"])
                op.execute(f'CREATE INDEX IF NOT EXISTS {idx_info["name"]} ON payments ({columns_str})')
    else:
        for idx_info in payment_indexes:
            if idx_info["name"] not in existing_payment_indexes:
                try:
                    op.create_index(
                        idx_info["name"],
                        "payments",
                        idx_info["columns"],
                        unique=False
                    )
                except Exception:
                    pass
    
    try:
        existing_expense_indexes = {idx["name"] for idx in inspector.get_indexes("expenses")}
    except Exception:
        existing_expense_indexes = set()
    
    expense_indexes = [
        {
            "name": "ix_expenses_partner_id_date",
            "columns": ["partner_id", "date"],
            "description": "Composite index for partner expenses with date filtering"
        },
        {
            "name": "ix_expenses_payee_type_entity_id",
            "columns": ["payee_type", "payee_entity_id"],
            "description": "Composite index for payee type and entity ID queries"
        }
    ]
    
    if is_sqlite:
        for idx_info in expense_indexes:
            if idx_info["name"] not in existing_expense_indexes:
                columns_str = ", ".join(idx_info["columns"])
                op.execute(f'CREATE INDEX IF NOT EXISTS {idx_info["name"]} ON expenses ({columns_str})')
    else:
        for idx_info in expense_indexes:
            if idx_info["name"] not in existing_expense_indexes:
                try:
                    op.create_index(
                        idx_info["name"],
                        "expenses",
                        idx_info["columns"],
                        unique=False
                    )
                except Exception:
                    pass
    
    try:
        bind.execute(sa_text("ANALYZE partners"))
    except Exception:
        pass
    
    try:
        bind.execute(sa_text("ANALYZE payments"))
    except Exception:
        pass
    
    try:
        bind.execute(sa_text("ANALYZE expenses"))
    except Exception:
        pass


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    
    try:
        existing_partner_indexes = {idx["name"] for idx in inspector.get_indexes("partners")}
    except Exception:
        existing_partner_indexes = set()
    
    partner_indexes_to_drop = [
        "ix_partners_is_archived_current_balance",
        "ix_partners_is_archived_name",
        "ix_partners_customer_id_current_balance",
        "ix_partners_currency_current_balance",
        "ix_partners_share_percentage"
    ]
    
    if is_sqlite:
        with op.batch_alter_table("partners") as batch_op:
            for idx_name in partner_indexes_to_drop:
                if idx_name in existing_partner_indexes:
                    try:
                        batch_op.drop_index(idx_name)
                    except Exception:
                        pass
    else:
        for idx_name in partner_indexes_to_drop:
            if idx_name in existing_partner_indexes:
                try:
                    op.drop_index(idx_name, table_name="partners")
                except Exception:
                    pass
    
    try:
        existing_payment_indexes = {idx["name"] for idx in inspector.get_indexes("payments")}
    except Exception:
        existing_payment_indexes = set()
    
    payment_indexes_to_drop = [
        "ix_payments_partner_id_status",
        "ix_payments_partner_id_direction",
        "ix_payments_partner_id_date"
    ]
    
    if is_sqlite:
        with op.batch_alter_table("payments") as batch_op:
            for idx_name in payment_indexes_to_drop:
                if idx_name in existing_payment_indexes:
                    try:
                        batch_op.drop_index(idx_name)
                    except Exception:
                        pass
    else:
        for idx_name in payment_indexes_to_drop:
            if idx_name in existing_payment_indexes:
                try:
                    op.drop_index(idx_name, table_name="payments")
                except Exception:
                    pass
    
    try:
        existing_expense_indexes = {idx["name"] for idx in inspector.get_indexes("expenses")}
    except Exception:
        existing_expense_indexes = set()
    
    expense_indexes_to_drop = [
        "ix_expenses_partner_id_date",
        "ix_expenses_payee_type_entity_id"
    ]
    
    if is_sqlite:
        with op.batch_alter_table("expenses") as batch_op:
            for idx_name in expense_indexes_to_drop:
                if idx_name in existing_expense_indexes:
                    try:
                        batch_op.drop_index(idx_name)
                    except Exception:
                        pass
    else:
        for idx_name in expense_indexes_to_drop:
            if idx_name in existing_expense_indexes:
                try:
                    op.drop_index(idx_name, table_name="expenses")
                except Exception:
                    pass

