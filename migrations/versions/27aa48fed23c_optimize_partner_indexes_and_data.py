"""optimize partner indexes and data

Revision ID: 27aa48fed23c
Revises: 20250121_partner_indexes
Create Date: 2025-11-19 02:29:32.129031

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text


revision = '27aa48fed23c'
down_revision = '20250121_partner_indexes'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    
    existing_partner_indexes = {idx["name"] for idx in inspector.get_indexes("partners")}
    
    redundant_indexes = []
    
    if "ix_partners_current_balance" in existing_partner_indexes:
        redundant_indexes.append("ix_partners_current_balance")
    
    redundant_balance_indexes = [
        "ix_partners_payments_out_balance",
        "ix_partners_payments_in_balance",
        "ix_partners_inventory_balance",
        "ix_partners_sales_share_balance",
        "ix_partners_opening_balance"
    ]
    
    for idx_name in redundant_balance_indexes:
        if idx_name in existing_partner_indexes:
            redundant_indexes.append(idx_name)
    
    if is_sqlite:
        for idx_name in redundant_indexes:
            try:
                op.execute(f'DROP INDEX IF EXISTS {idx_name}')
            except Exception:
                pass
    else:
        for idx_name in redundant_indexes:
            try:
                op.drop_index(idx_name, table_name="partners")
            except Exception:
                pass
    
    optimized_indexes = [
        {
            "name": "ix_partners_is_archived_name",
            "columns": ["is_archived", "name"],
            "priority": 1,
            "description": "Most common query: filter by archived + sort by name"
        },
        {
            "name": "ix_partners_is_archived_current_balance",
            "columns": ["is_archived", "current_balance"],
            "priority": 2,
            "description": "Filter by archived + sort by balance"
        },
        {
            "name": "ix_partners_name_phone",
            "columns": ["name", "phone_number"],
            "priority": 3,
            "description": "Search by name and phone"
        },
        {
            "name": "ix_partners_customer_id",
            "columns": ["customer_id"],
            "priority": 4,
            "description": "Link to customers"
        },
        {
            "name": "ix_partners_currency_current_balance",
            "columns": ["currency", "current_balance"],
            "priority": 5,
            "description": "Currency-based balance queries"
        },
        {
            "name": "ix_partners_share_percentage",
            "columns": ["share_percentage"],
            "priority": 6,
            "description": "Filter by share percentage"
        }
    ]
    
    optimized_indexes.sort(key=lambda x: x["priority"])
    
    if is_sqlite:
        for idx_info in optimized_indexes:
            if idx_info["name"] not in existing_partner_indexes:
                columns_str = ", ".join(idx_info["columns"])
                op.execute(f'CREATE INDEX IF NOT EXISTS {idx_info["name"]} ON partners ({columns_str})')
    else:
        for idx_info in optimized_indexes:
            if idx_info["name"] not in existing_partner_indexes:
                try:
                    op.create_index(
                        idx_info["name"],
                        "partners",
                        idx_info["columns"],
                        unique=False
                    )
                except Exception:
                    pass
    
    _optimize_checks_indexes(bind, inspector, is_sqlite)
    _optimize_legacy_data(bind)


def _optimize_checks_indexes(bind, inspector, is_sqlite):
    try:
        existing_check_indexes = {idx["name"] for idx in inspector.get_indexes("checks")}
        
        check_indexes = [
            {
                "name": "ix_checks_status_due_date_direction",
                "columns": ["status", "check_due_date", "direction"],
                "priority": 1,
                "description": "Most common: filter by status + sort by due_date + direction"
            },
            {
                "name": "ix_checks_customer_id_date",
                "columns": ["customer_id", "check_date"],
                "priority": 2,
                "description": "Filter by customer + date"
            },
            {
                "name": "ix_checks_supplier_id_date",
                "columns": ["supplier_id", "check_date"],
                "priority": 3,
                "description": "Filter by supplier + date"
            },
            {
                "name": "ix_checks_partner_id_date",
                "columns": ["partner_id", "check_date"],
                "priority": 4,
                "description": "Filter by partner + date"
            },
            {
                "name": "ix_checks_payment_id_status",
                "columns": ["payment_id", "status"],
                "priority": 5,
                "description": "Filter by payment + status"
            },
            {
                "name": "ix_checks_is_archived_status",
                "columns": ["is_archived", "status"],
                "priority": 6,
                "description": "Filter archived + status"
            },
            {
                "name": "ix_checks_check_date_status",
                "columns": ["check_date", "status"],
                "priority": 7,
                "description": "Filter by date + status"
            }
        ]
        
        check_indexes.sort(key=lambda x: x["priority"])
        
        if is_sqlite:
            for idx_info in check_indexes:
                if idx_info["name"] not in existing_check_indexes:
                    columns_str = ", ".join([col for col in idx_info["columns"] if col])
                    if columns_str:
                        op.execute(f'CREATE INDEX IF NOT EXISTS {idx_info["name"]} ON checks ({columns_str})')
        else:
            for idx_info in check_indexes:
                if idx_info["name"] not in existing_check_indexes:
                    try:
                        columns = [col for col in idx_info["columns"] if col]
                        if columns:
                            op.create_index(
                                idx_info["name"],
                                "checks",
                                columns,
                                unique=False
                            )
                    except Exception:
                        pass
    except Exception:
        pass


def _optimize_legacy_data(connection):
    try:
        try:
            from models import _ensure_customer_for_counterparty, normalize_phone, normalize_email
        except Exception:
            _ensure_customer_for_counterparty = None
            normalize_phone = lambda x: (x or "").strip() if x else None
            normalize_email = lambda x: (x or "").strip().lower() if x else None
        
        partners = connection.execute(sa_text("SELECT id, name, phone_number, email, address, currency, customer_id FROM partners")).fetchall()
        suppliers = connection.execute(sa_text("SELECT id, name, phone, email, address, currency, customer_id FROM suppliers")).fetchall()
        
        total_partners = len(partners)
        total_suppliers = len(suppliers)
        linked_partners = 0
        linked_suppliers = 0
        already_linked_partners = 0
        already_linked_suppliers = 0
        errors = 0
        
        for (partner_id, name, phone, email, address, currency, customer_id) in partners:
            try:
                partner_id_int = int(partner_id)
                
                if customer_id:
                    already_linked_partners += 1
                    continue
                
                if not _ensure_customer_for_counterparty:
                    continue
                
                try:
                    customer_id = None
                    normalized_phone = normalize_phone(phone) if phone else None
                    
                    if normalized_phone:
                        existing_customer = connection.execute(
                            sa_text("SELECT id FROM customers WHERE phone = :phone LIMIT 1"),
                            {"phone": normalized_phone}
                        ).fetchone()
                        
                        if existing_customer:
                            customer_id = existing_customer[0]
                    
                    if not customer_id and name:
                        name_clean = (name or "").strip()
                        if name_clean:
                            existing_customer = connection.execute(
                                sa_text("SELECT id FROM customers WHERE LOWER(TRIM(name)) = LOWER(:name) LIMIT 1"),
                                {"name": name_clean}
                            ).fetchone()
                            
                            if existing_customer:
                                customer_id = existing_customer[0]
                    
                    if not customer_id:
                        customer_id = _ensure_customer_for_counterparty(
                            connection,
                            name=name or "",
                            phone=normalized_phone or "",
                            whatsapp=normalized_phone or "",
                            email=normalize_email(email) if email else None,
                            address=(address or "").strip() or None,
                            currency=(currency or "ILS").upper(),
                            source_label="PARTNER",
                            source_id=partner_id_int,
                        )
                    
                    if customer_id:
                        connection.execute(
                            sa_text("UPDATE partners SET customer_id = :customer_id WHERE id = :id"),
                            {"customer_id": customer_id, "id": partner_id_int}
                        )
                        linked_partners += 1
                except Exception as e:
                    errors += 1
                    try:
                        print(f"Error linking partner {partner_id}: {str(e)}")
                    except:
                        pass
            except Exception as e:
                errors += 1
                try:
                    print(f"Error optimizing partner {partner_id}: {str(e)}")
                except:
                    pass
                continue
        
        for (supplier_id, name, phone, email, address, currency, customer_id) in suppliers:
            try:
                supplier_id_int = int(supplier_id)
                
                if customer_id:
                    already_linked_suppliers += 1
                    continue
                
                if not _ensure_customer_for_counterparty:
                    continue
                
                try:
                    customer_id = None
                    normalized_phone = normalize_phone(phone) if phone else None
                    
                    if normalized_phone:
                        existing_customer = connection.execute(
                            sa_text("SELECT id FROM customers WHERE phone = :phone LIMIT 1"),
                            {"phone": normalized_phone}
                        ).fetchone()
                        
                        if existing_customer:
                            customer_id = existing_customer[0]
                    
                    if not customer_id and name:
                        name_clean = (name or "").strip()
                        if name_clean:
                            existing_customer = connection.execute(
                                sa_text("SELECT id FROM customers WHERE LOWER(TRIM(name)) = LOWER(:name) LIMIT 1"),
                                {"name": name_clean}
                            ).fetchone()
                            
                            if existing_customer:
                                customer_id = existing_customer[0]
                    
                    if not customer_id:
                        customer_id = _ensure_customer_for_counterparty(
                            connection,
                            name=name or "",
                            phone=normalized_phone or "",
                            whatsapp=normalized_phone or "",
                            email=normalize_email(email) if email else None,
                            address=(address or "").strip() or None,
                            currency=(currency or "ILS").upper(),
                            source_label="SUPPLIER",
                            source_id=supplier_id_int,
                        )
                    
                    if customer_id:
                        connection.execute(
                            sa_text("UPDATE suppliers SET customer_id = :customer_id WHERE id = :id"),
                            {"customer_id": customer_id, "id": supplier_id_int}
                        )
                        linked_suppliers += 1
                except Exception as e:
                    errors += 1
                    try:
                        print(f"Error linking supplier {supplier_id}: {str(e)}")
                    except:
                        pass
            except Exception as e:
                errors += 1
                try:
                    print(f"Error optimizing supplier {supplier_id}: {str(e)}")
                except:
                    pass
                continue
        
        connection.commit()
        try:
            print(f"Optimized data:")
            print(f"  - Partners: {total_partners} total, {already_linked_partners} already linked, {linked_partners} newly linked")
            print(f"  - Suppliers: {total_suppliers} total, {already_linked_suppliers} already linked, {linked_suppliers} newly linked")
            if errors > 0:
                print(f"  - Errors: {errors}")
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
    is_sqlite = bind.dialect.name == "sqlite"
    
    try:
        existing_partner_indexes = {idx["name"] for idx in inspector.get_indexes("partners")}
    except Exception:
        existing_partner_indexes = set()
    
    indexes_to_drop = [
        "ix_partners_is_archived_name",
        "ix_partners_is_archived_current_balance",
        "ix_partners_name_phone",
        "ix_partners_customer_id",
        "ix_partners_currency_current_balance",
        "ix_partners_share_percentage"
    ]
    
    check_indexes_to_drop = [
        "ix_checks_status_due_date_direction",
        "ix_checks_customer_id_date",
        "ix_checks_supplier_id_date",
        "ix_checks_partner_id_date",
        "ix_checks_payment_id_status",
        "ix_checks_is_archived_status",
        "ix_checks_check_date_status"
    ]
    
    if is_sqlite:
        for idx_name in indexes_to_drop:
            if idx_name in existing_partner_indexes:
                try:
                    op.execute(f'DROP INDEX IF EXISTS {idx_name}')
                except Exception:
                    pass
    else:
        for idx_name in indexes_to_drop:
            if idx_name in existing_partner_indexes:
                try:
                    op.drop_index(idx_name, table_name="partners")
                except Exception:
                    pass
    
    try:
        existing_check_indexes = {idx["name"] for idx in inspector.get_indexes("checks")}
    except Exception:
        existing_check_indexes = set()
    
    if is_sqlite:
        for idx_name in check_indexes_to_drop:
            if idx_name in existing_check_indexes:
                try:
                    op.execute(f'DROP INDEX IF EXISTS {idx_name}')
                except Exception:
                    pass
    else:
        for idx_name in check_indexes_to_drop:
            if idx_name in existing_check_indexes:
                try:
                    op.drop_index(idx_name, table_name="checks")
                except Exception:
                    pass
