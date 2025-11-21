"""optimize service and ledger indexes

Revision ID: 46df8ed7e7e5
Revises: 77ab4f532fc4
Create Date: 2025-11-19 02:50:24.472610

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text


revision = '46df8ed7e7e5'
down_revision = '77ab4f532fc4'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    
    _optimize_service_indexes(bind, inspector, is_sqlite)
    _optimize_ledger_indexes(bind, inspector, is_sqlite)


def _optimize_service_indexes(connection, inspector, is_sqlite):
    try:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("service_requests")}
    except Exception:
        existing_indexes = set()
    
    service_indexes = [
        {
            "name": "ix_service_requests_customer_id_status_received_at",
            "columns": ["customer_id", "status", "received_at"],
            "priority": 1,
            "description": "Most common: filter by customer + status + sort by date"
        },
        {
            "name": "ix_service_requests_customer_id_received_at",
            "columns": ["customer_id", "received_at"],
            "priority": 2,
            "description": "Filter by customer + sort by date"
        },
        {
            "name": "ix_service_requests_status_created_at",
            "columns": ["status", "created_at"],
            "priority": 3,
            "description": "Filter by status + sort by creation date"
        },
        {
            "name": "ix_service_requests_mechanic_id_status",
            "columns": ["mechanic_id", "status"],
            "priority": 4,
            "description": "Filter by mechanic + status"
        },
        {
            "name": "ix_service_requests_status_priority",
            "columns": ["status", "priority"],
            "priority": 5,
            "description": "Filter by status + priority"
        },
        {
            "name": "ix_service_requests_received_at_status",
            "columns": ["received_at", "status"],
            "priority": 6,
            "description": "Date range queries with status"
        }
    ]
    
    service_indexes.sort(key=lambda x: x["priority"])
    
    if is_sqlite:
        for idx_info in service_indexes:
            if idx_info["name"] not in existing_indexes:
                columns_str = ", ".join(idx_info["columns"])
                op.execute(f'CREATE INDEX IF NOT EXISTS {idx_info["name"]} ON service_requests ({columns_str})')
    else:
        for idx_info in service_indexes:
            if idx_info["name"] not in existing_indexes:
                try:
                    op.create_index(
                        idx_info["name"],
                        "service_requests",
                        idx_info["columns"],
                        unique=False
                    )
                except Exception:
                    pass


def _optimize_ledger_indexes(connection, inspector, is_sqlite):
    try:
        existing_batch_indexes = {idx["name"] for idx in inspector.get_indexes("gl_batches")}
    except Exception:
        existing_batch_indexes = set()
    
    batch_indexes = [
        {
            "name": "ix_gl_batches_status_posted_at",
            "columns": ["status", "posted_at"],
            "priority": 1,
            "description": "Most common: filter by status + sort by date"
        },
        {
            "name": "ix_gl_batches_entity_type_entity_id_posted_at",
            "columns": ["entity_type", "entity_id", "posted_at"],
            "priority": 2,
            "description": "Entity ledger queries with date sorting"
        },
        {
            "name": "ix_gl_batches_source_type_posted_at",
            "columns": ["source_type", "posted_at"],
            "priority": 3,
            "description": "Filter by source type + sort by date"
        },
        {
            "name": "ix_gl_batches_posted_at_status",
            "columns": ["posted_at", "status"],
            "priority": 4,
            "description": "Date range queries with status"
        }
    ]
    
    batch_indexes.sort(key=lambda x: x["priority"])
    
    if is_sqlite:
        for idx_info in batch_indexes:
            if idx_info["name"] not in existing_batch_indexes:
                columns_str = ", ".join(idx_info["columns"])
                op.execute(f'CREATE INDEX IF NOT EXISTS {idx_info["name"]} ON gl_batches ({columns_str})')
    else:
        for idx_info in batch_indexes:
            if idx_info["name"] not in existing_batch_indexes:
                try:
                    op.create_index(
                        idx_info["name"],
                        "gl_batches",
                        idx_info["columns"],
                        unique=False
                    )
                except Exception:
                    pass
    
    try:
        existing_entry_indexes = {idx["name"] for idx in inspector.get_indexes("gl_entries")}
    except Exception:
        existing_entry_indexes = set()
    
    entry_indexes = [
        {
            "name": "ix_gl_entries_account_batch_id",
            "columns": ["account", "batch_id"],
            "priority": 1,
            "description": "Account queries with batch join"
        },
        {
            "name": "ix_gl_entries_batch_id_account",
            "columns": ["batch_id", "account"],
            "priority": 2,
            "description": "Batch queries with account filter"
        }
    ]
    
    entry_indexes.sort(key=lambda x: x["priority"])
    
    if is_sqlite:
        for idx_info in entry_indexes:
            if idx_info["name"] not in existing_entry_indexes:
                columns_str = ", ".join(idx_info["columns"])
                op.execute(f'CREATE INDEX IF NOT EXISTS {idx_info["name"]} ON gl_entries ({columns_str})')
    else:
        for idx_info in entry_indexes:
            if idx_info["name"] not in existing_entry_indexes:
                try:
                    op.create_index(
                        idx_info["name"],
                        "gl_entries",
                        idx_info["columns"],
                        unique=False
                    )
                except Exception:
                    pass
    
    try:
        connection.execute(sa_text("ANALYZE service_requests"))
    except Exception:
        pass
    
    try:
        connection.execute(sa_text("ANALYZE gl_batches"))
    except Exception:
        pass
    
    try:
        connection.execute(sa_text("ANALYZE gl_entries"))
    except Exception:
        pass
    
    # دمج WAL في الملف الرئيسي بعد إضافة الفهارس
    try:
        connection.execute(sa_text("PRAGMA wal_checkpoint(TRUNCATE)"))
    except Exception:
        pass


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    
    service_indexes_to_drop = [
        "ix_service_requests_customer_id_status_received_at",
        "ix_service_requests_customer_id_received_at",
        "ix_service_requests_status_created_at",
        "ix_service_requests_mechanic_id_status",
        "ix_service_requests_status_priority",
        "ix_service_requests_received_at_status"
    ]
    
    batch_indexes_to_drop = [
        "ix_gl_batches_status_posted_at",
        "ix_gl_batches_entity_type_entity_id_posted_at",
        "ix_gl_batches_source_type_posted_at",
        "ix_gl_batches_posted_at_status"
    ]
    
    entry_indexes_to_drop = [
        "ix_gl_entries_account_batch_id",
        "ix_gl_entries_batch_id_account"
    ]
    
    if is_sqlite:
        for idx_name in service_indexes_to_drop:
            try:
                op.execute(f'DROP INDEX IF EXISTS {idx_name}')
            except Exception:
                pass
        
        for idx_name in batch_indexes_to_drop:
            try:
                op.execute(f'DROP INDEX IF EXISTS {idx_name}')
            except Exception:
                pass
        
        for idx_name in entry_indexes_to_drop:
            try:
                op.execute(f'DROP INDEX IF EXISTS {idx_name}')
            except Exception:
                pass
    else:
        for idx_name in service_indexes_to_drop:
            try:
                op.drop_index(idx_name, table_name="service_requests")
            except Exception:
                pass
        
        for idx_name in batch_indexes_to_drop:
            try:
                op.drop_index(idx_name, table_name="gl_batches")
            except Exception:
                pass
        
        for idx_name in entry_indexes_to_drop:
            try:
                op.drop_index(idx_name, table_name="gl_entries")
            except Exception:
                pass
