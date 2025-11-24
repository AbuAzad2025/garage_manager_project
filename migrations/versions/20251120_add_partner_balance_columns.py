"""add partner balance columns

Revision ID: 20251120_partner_balance_cols
Revises: 20251119_supplier_balance_cols
Create Date: 2025-11-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text
from decimal import Decimal


revision = '20251120_partner_balance_cols'
down_revision = '20251119_supplier_balance_cols'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("partners")}
    is_sqlite = bind.dialect.name == "sqlite"
    
    balance_columns = [
        ("current_balance", sa.Numeric(12, 2), True),
        ("inventory_balance", sa.Numeric(12, 2), False),
        ("sales_share_balance", sa.Numeric(12, 2), False),
        ("sales_to_partner_balance", sa.Numeric(12, 2), False),
        ("service_fees_balance", sa.Numeric(12, 2), False),
        ("preorders_to_partner_balance", sa.Numeric(12, 2), False),
        ("preorders_prepaid_balance", sa.Numeric(12, 2), False),
        ("damaged_items_balance", sa.Numeric(12, 2), False),
        ("payments_in_balance", sa.Numeric(12, 2), False),
        ("payments_out_balance", sa.Numeric(12, 2), False),
        ("returned_checks_in_balance", sa.Numeric(12, 2), False),
        ("returned_checks_out_balance", sa.Numeric(12, 2), False),
        ("expenses_balance", sa.Numeric(12, 2), False),
        ("service_expenses_balance", sa.Numeric(12, 2), False),
    ]
    
    if is_sqlite:
        for col_name, col_type, create_index in balance_columns:
            if col_name not in columns:
                op.execute(f'ALTER TABLE partners ADD COLUMN {col_name} NUMERIC(12, 2) NOT NULL DEFAULT 0')
    else:
        for col_name, col_type, create_index in balance_columns:
            if col_name not in columns:
                op.add_column("partners", sa.Column(col_name, col_type, nullable=False, server_default=sa_text("0")))
    
    _calculate_initial_balances(bind)


def _calculate_initial_balances(connection):
    try:
        partners = connection.execute(sa_text("SELECT id FROM partners")).fetchall()
        total = len(partners)
        updated = 0
        
        for (partner_id,) in partners:
            try:
                partner_id_int = int(partner_id)
                
                connection.execute(
                    sa_text("""
                        UPDATE partners SET
                            current_balance = COALESCE(opening_balance, 0),
                            inventory_balance = 0,
                            sales_share_balance = 0,
                            sales_to_partner_balance = 0,
                            service_fees_balance = 0,
                            preorders_to_partner_balance = 0,
                            preorders_prepaid_balance = 0,
                            damaged_items_balance = 0,
                            payments_in_balance = 0,
                            payments_out_balance = 0,
                            returned_checks_in_balance = 0,
                            returned_checks_out_balance = 0,
                            expenses_balance = 0,
                            service_expenses_balance = 0
                        WHERE id = :id
                    """),
                    {"id": partner_id_int}
                )
                updated += 1
            except Exception:
                continue
        
        connection.commit()
        try:
            print(f"Initialized {updated}/{total} partners balance columns")
        except:
            pass
    except Exception as e:
        try:
            connection.rollback()
            print(f"Migration error: {str(e)}")
        except:
            pass


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("partners")}
    is_sqlite = bind.dialect.name == "sqlite"
    
    balance_columns = [
        "current_balance",
        "inventory_balance",
        "sales_share_balance",
        "sales_to_partner_balance",
        "service_fees_balance",
        "preorders_to_partner_balance",
        "preorders_prepaid_balance",
        "damaged_items_balance",
        "payments_in_balance",
        "payments_out_balance",
        "returned_checks_in_balance",
        "returned_checks_out_balance",
        "expenses_balance",
        "service_expenses_balance"
    ]
    
    if is_sqlite:
        with op.batch_alter_table("partners") as batch_op:
            indexes = {idx["name"] for idx in inspector.get_indexes("partners")}
            if "ix_partners_current_balance" in indexes:
                batch_op.drop_index("ix_partners_current_balance")
            
            for col_name in balance_columns:
                if col_name in columns:
                    batch_op.drop_column(col_name)
    else:
        indexes = {idx["name"] for idx in inspector.get_indexes("partners")}
        if "ix_partners_current_balance" in indexes:
            op.drop_index("ix_partners_current_balance", table_name="partners")
        
        for col_name in balance_columns:
            if col_name in columns:
                op.drop_column("partners", col_name)

