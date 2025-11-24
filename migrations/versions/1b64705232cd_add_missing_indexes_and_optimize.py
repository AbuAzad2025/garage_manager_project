"""add_missing_indexes_and_optimize

Revision ID: 1b64705232cd
Revises: 86dd195d861b
Create Date: 2025-11-24 03:19:59.589792

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b64705232cd'
down_revision = '86dd195d861b'
branch_labels = None
depends_on = None


def _create_index_if_not_exists(conn, table_name, index_name, columns):
    inspector = sa.inspect(conn)
    
    if table_name not in inspector.get_table_names():
        return False
    
    existing_indexes = inspector.get_indexes(table_name)
    existing_names = {idx['name'] for idx in existing_indexes}
    
    if index_name in existing_names:
        return False
    
    try:
        cols_str = ", ".join(columns)
        sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({cols_str})"
        conn.execute(sa.text(sql))
        return True
    except Exception:
        return False


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    indexes_to_create = [
        ("asset_maintenance", "ix_asset_maintenance_asset_id", ["asset_id"]),
        ("asset_maintenance", "ix_asset_maintenance_next_maintenance_date", ["next_maintenance_date"]),
        ("asset_maintenance", "ix_asset_maintenance_expense_id", ["expense_id"]),
        ("asset_maintenance", "ix_maintenance_asset_date", ["asset_id", "maintenance_date"]),
        ("asset_maintenance", "ix_asset_maintenance_maintenance_date", ["maintenance_date"]),
        ("asset_maintenance", "ix_asset_maintenance_updated_at", ["updated_at"]),
        ("asset_maintenance", "ix_asset_maintenance_maintenance_type", ["maintenance_type"]),
        ("asset_maintenance", "ix_asset_maintenance_created_at", ["created_at"]),
        
        ("bank_statements", "ix_bank_statements_updated_by", ["updated_by"]),
        ("bank_statements", "ix_bank_statements_created_by", ["created_by"]),
        
        ("bank_transactions", "ix_bank_transactions_gl_batch_id", ["gl_batch_id"]),
        ("bank_transactions", "ix_bank_transactions_statement_id", ["statement_id"]),
        ("bank_transactions", "ix_bank_transactions_payment_id", ["payment_id"]),
        ("bank_transactions", "ix_bank_transactions_value_date", ["value_date"]),
        ("bank_transactions", "ix_bank_transactions_matched", ["matched"]),
        ("bank_transactions", "ix_bank_transactions_updated_at", ["updated_at"]),
        ("bank_transactions", "ix_bank_tx_account_date", ["bank_account_id", "transaction_date"]),
        ("bank_transactions", "ix_bank_transactions_transaction_date", ["transaction_date"]),
        ("bank_transactions", "ix_bank_tx_matched", ["bank_account_id", "matched"]),
        ("bank_transactions", "ix_bank_transactions_bank_account_id", ["bank_account_id"]),
    ]
    
    created = 0
    skipped = 0
    
    for table_name, index_name, columns in indexes_to_create:
        if _create_index_if_not_exists(conn, table_name, index_name, columns):
            created += 1
        else:
            skipped += 1
    
    try:
        conn.execute(sa.text("PRAGMA optimize"))
        conn.execute(sa.text("PRAGMA wal_checkpoint(TRUNCATE)"))
    except Exception:
        pass
    
    try:
        print(f"Created {created} new indexes")
        if skipped > 0:
            print(f"Skipped {skipped} indexes (already exist or table missing)")
    except:
        pass


def downgrade():
    pass
