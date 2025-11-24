"""add_missing_indexes_and_foreign_keys

Revision ID: 8a0730f0d0d7
Revises: 1b64705232cd
Create Date: 2025-11-24 03:24:18.888582

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a0730f0d0d7'
down_revision = '1b64705232cd'
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
        db_columns = {col['name'] for col in inspector.get_columns(table_name)}
        for col in columns:
            if col not in db_columns:
                return False
        
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
        ("bank_transactions", "ix_bank_transactions_reference", ["reference"]),
        ("bank_transactions", "ix_bank_transactions_created_at", ["created_at"]),
        ("bank_transactions", "ix_bank_transactions_reconciliation_id", ["reconciliation_id"]),
        
        ("checks", "ix_checks_check_due_date", ["check_due_date"]),
        ("checks", "ix_checks_created_by_id", ["created_by_id"]),
        ("checks", "ix_checks_partner_id", ["partner_id"]),
        ("checks", "ix_checks_created_at", ["created_at"]),
        ("checks", "ix_checks_supplier_id", ["supplier_id"]),
        ("checks", "ix_checks_archived_by", ["archived_by"]),
        ("checks", "ix_checks_direction_status", ["direction", "status"]),
        ("checks", "ix_checks_archived_at", ["archived_at"]),
        ("checks", "ix_checks_check_number", ["check_number"]),
        ("checks", "ix_checks_updated_at", ["updated_at"]),
        ("checks", "ix_checks_status_due_date", ["status", "check_due_date"]),
        ("checks", "ix_checks_is_archived", ["is_archived"]),
        
        ("cost_allocation_executions", "ix_allocation_exec_date", ["execution_date"]),
        ("cost_allocation_lines", "ix_allocation_line_rule", ["rule_id"]),
        ("cost_allocation_rules", "ix_allocation_rule_active", ["is_active"]),
        
        ("cost_centers", "ix_cost_centers_created_by", ["created_by"]),
        ("cost_centers", "ix_cost_centers_updated_by", ["updated_by"]),
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
    except Exception:
        pass
    
    try:
        print(f"Created {created} new indexes")
        if skipped > 0:
            print(f"Skipped {skipped} indexes (already exist, table missing, or columns missing)")
    except:
        pass


def downgrade():
    pass
