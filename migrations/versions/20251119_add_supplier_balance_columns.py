"""add supplier balance columns

Revision ID: 20251119_supplier_balance_cols
Revises: 20251118_customer_balance_cols
Create Date: 2025-11-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text as sa_text
from decimal import Decimal


revision = '20251119_supplier_balance_cols'
down_revision = '20251118_customer_balance_cols'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("suppliers")}
    is_sqlite = bind.dialect.name == "sqlite"
    
    balance_columns = [
        ("current_balance", sa.Numeric(12, 2), True),
        ("exchange_items_balance", sa.Numeric(12, 2), False),
        ("sale_returns_balance", sa.Numeric(12, 2), False),
        ("sales_balance", sa.Numeric(12, 2), False),
        ("services_balance", sa.Numeric(12, 2), False),
        ("preorders_balance", sa.Numeric(12, 2), False),
        ("payments_in_balance", sa.Numeric(12, 2), False),
        ("payments_out_balance", sa.Numeric(12, 2), False),
        ("preorders_prepaid_balance", sa.Numeric(12, 2), False),
        ("returns_balance", sa.Numeric(12, 2), False),
        ("expenses_balance", sa.Numeric(12, 2), False),
        ("returned_checks_in_balance", sa.Numeric(12, 2), False),
        ("returned_checks_out_balance", sa.Numeric(12, 2), False),
    ]
    
    if is_sqlite:
        for col_name, col_type, create_index in balance_columns:
            if col_name not in columns:
                op.execute(f'ALTER TABLE suppliers ADD COLUMN {col_name} NUMERIC(12, 2) NOT NULL DEFAULT 0')
        
        indexes = {idx["name"] for idx in inspector.get_indexes("suppliers")}
        if "ix_suppliers_current_balance" not in indexes:
            op.execute('CREATE INDEX IF NOT EXISTS ix_suppliers_current_balance ON suppliers (current_balance)')
    else:
        for col_name, col_type, create_index in balance_columns:
            if col_name not in columns:
                op.add_column("suppliers", sa.Column(col_name, col_type, nullable=False, server_default=sa_text("0")))
        
        indexes = {idx["name"] for idx in inspector.get_indexes("suppliers")}
        if "ix_suppliers_current_balance" not in indexes:
            op.create_index("ix_suppliers_current_balance", "suppliers", ["current_balance"])
    
    _calculate_initial_balances(bind)


def _calculate_initial_balances(connection):
    try:
        import sys
        import os
        import importlib.util
        from datetime import datetime
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        
        suppliers = connection.execute(sa_text("SELECT id FROM suppliers")).fetchall()
        total = len(suppliers)
        updated = 0
        errors = 0
        
        for (supplier_id,) in suppliers:
            try:
                supplier_id_int = int(supplier_id)
                
                supplier_data = connection.execute(
                    sa_text("SELECT opening_balance, currency FROM suppliers WHERE id = :id"),
                    {"id": supplier_id_int}
                ).fetchone()
                
                if not supplier_data:
                    continue
                
                opening_balance = Decimal(str(supplier_data[0] or 0))
                supplier_currency = supplier_data[1] if len(supplier_data) > 1 and supplier_data[1] else "ILS"
                
                supplier_settlements_path = os.path.join(base_dir, 'routes', 'supplier_settlements.py')
                if not os.path.exists(supplier_settlements_path):
                    continue
                
                spec = importlib.util.spec_from_file_location("supplier_settlements", supplier_settlements_path)
                supplier_settlements_module = importlib.util.module_from_spec(spec)
                sys.modules["supplier_settlements"] = supplier_settlements_module
                spec.loader.exec_module(supplier_settlements_module)
                
                _calculate_smart_supplier_balance = supplier_settlements_module._calculate_smart_supplier_balance
                
                date_from = datetime(2024, 1, 1)
                date_to = datetime.utcnow()
                
                balance_data = _calculate_smart_supplier_balance(supplier_id_int, date_from, date_to)
                
                if not balance_data.get("success"):
                    continue
                
                if supplier_currency != "ILS" and opening_balance != 0:
                    try:
                        models_path = os.path.join(base_dir, 'models.py')
                        if os.path.exists(models_path):
                            spec = importlib.util.spec_from_file_location("models", models_path)
                            models_module = importlib.util.module_from_spec(spec)
                            sys.modules["models"] = models_module
                            spec.loader.exec_module(models_module)
                            opening_balance = models_module.convert_amount(opening_balance, supplier_currency, "ILS", date_from)
                    except Exception:
                        pass
                
                exchange_items = Decimal(str(balance_data.get("rights", {}).get("exchange_items", {}).get("total_value_ils", 0) or 0))
                sales = Decimal(str(balance_data.get("obligations", {}).get("sales_to_supplier", {}).get("total_ils", 0) or 0))
                services = Decimal(str(balance_data.get("obligations", {}).get("services_to_supplier", {}).get("total_ils", 0) or 0))
                preorders = Decimal(str(balance_data.get("obligations", {}).get("preorders_to_supplier", {}).get("total_ils", 0) or 0) if isinstance(balance_data.get("obligations", {}).get("preorders_to_supplier"), dict) else 0)
                payments_in = Decimal(str(balance_data.get("payments", {}).get("total_received", 0) or 0))
                payments_out = Decimal(str(balance_data.get("payments", {}).get("total_paid", 0) or 0))
                preorders_prepaid = Decimal(str(balance_data.get("payments", {}).get("preorders_prepaid", {}).get("total_ils", 0) or 0))
                returns = Decimal(str(balance_data.get("payments", {}).get("returns_to_supplier", {}).get("total_value_ils", 0) or 0))
                expenses = Decimal(str(balance_data.get("expenses", {}).get("total_ils", 0) or 0))
                returned_checks_in = Decimal(str(balance_data.get("payments", {}).get("total_returned_checks_in", 0) or 0))
                returned_checks_out = Decimal(str(balance_data.get("payments", {}).get("total_returned_checks_out", 0) or 0))
                
                sale_returns = Decimal('0.00')
                try:
                    supplier_obj = connection.execute(
                        sa_text("SELECT customer_id FROM suppliers WHERE id = :id"),
                        {"id": supplier_id_int}
                    ).fetchone()
                    if supplier_obj and supplier_obj[0]:
                        sale_returns_ils = connection.execute(
                            sa_text("""
                                SELECT COALESCE(SUM(total_amount), 0) 
                                FROM sale_returns 
                                WHERE customer_id = :cid 
                                AND status = 'CONFIRMED'
                                AND currency = 'ILS'
                            """),
                            {"cid": supplier_obj[0]}
                        ).fetchone()
                        if sale_returns_ils:
                            sale_returns += Decimal(str(sale_returns_ils[0] or 0))
                        
                        sale_returns_other = connection.execute(
                            sa_text("""
                                SELECT total_amount, currency, created_at
                                FROM sale_returns 
                                WHERE customer_id = :cid 
                                AND status = 'CONFIRMED'
                                AND currency != 'ILS'
                            """),
                            {"cid": supplier_obj[0]}
                        ).fetchall()
                        
                        for row in sale_returns_other:
                            amt = Decimal(str(row[0] or 0))
                            curr = row[1] if len(row) > 1 else 'ILS'
                            date_val = row[2] if len(row) > 2 else date_from
                            try:
                                if curr != 'ILS':
                                    models_path = os.path.join(base_dir, 'models.py')
                                    if os.path.exists(models_path):
                                        spec = importlib.util.spec_from_file_location("models", models_path)
                                        models_module = importlib.util.module_from_spec(spec)
                                        sys.modules["models"] = models_module
                                        spec.loader.exec_module(models_module)
                                        amt = models_module.convert_amount(amt, curr, "ILS", date_val)
                            except Exception:
                                pass
                            sale_returns += amt
                except Exception:
                    pass
                
                current_balance = (
                    opening_balance +
                    exchange_items +
                    sale_returns -
                    sales -
                    services -
                    preorders +
                    payments_in -
                    payments_out +
                    preorders_prepaid -
                    returns +
                    expenses -
                    returned_checks_in +
                    returned_checks_out
                )
                
                connection.execute(
                    sa_text("""
                        UPDATE suppliers SET
                            exchange_items_balance = :exchange_items,
                            sale_returns_balance = :sale_returns,
                            sales_balance = :sales,
                            services_balance = :services,
                            preorders_balance = :preorders,
                            payments_in_balance = :payments_in,
                            payments_out_balance = :payments_out,
                            preorders_prepaid_balance = :preorders_prepaid,
                            returns_balance = :returns,
                            expenses_balance = :expenses,
                            returned_checks_in_balance = :returned_checks_in,
                            returned_checks_out_balance = :returned_checks_out,
                            current_balance = :current_balance
                        WHERE id = :id
                    """),
                    {
                        "id": supplier_id_int,
                        "exchange_items": float(exchange_items),
                        "sale_returns": float(sale_returns),
                        "sales": float(sales),
                        "services": float(services),
                        "preorders": float(preorders),
                        "payments_in": float(payments_in),
                        "payments_out": float(payments_out),
                        "preorders_prepaid": float(preorders_prepaid),
                        "returns": float(returns),
                        "expenses": float(expenses),
                        "returned_checks_in": float(returned_checks_in),
                        "returned_checks_out": float(returned_checks_out),
                        "current_balance": float(current_balance)
                    }
                )
                updated += 1
            except Exception as e:
                errors += 1
                try:
                    print(f"Error updating supplier {supplier_id}: {str(e)}")
                except:
                    pass
                continue
        
        connection.commit()
        try:
            print(f"Updated {updated}/{total} suppliers balance columns")
            if errors > 0:
                print(f"Errors: {errors}")
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
    columns = {col["name"] for col in inspector.get_columns("suppliers")}
    is_sqlite = bind.dialect.name == "sqlite"
    
    balance_columns = [
        "current_balance",
        "exchange_items_balance",
        "sale_returns_balance",
        "sales_balance",
        "services_balance",
        "preorders_balance",
        "payments_in_balance",
        "payments_out_balance",
        "preorders_prepaid_balance",
        "returns_balance",
        "expenses_balance",
        "returned_checks_in_balance",
        "returned_checks_out_balance"
    ]
    
    if is_sqlite:
        with op.batch_alter_table("suppliers") as batch_op:
            indexes = {idx["name"] for idx in inspector.get_indexes("suppliers")}
            if "ix_suppliers_current_balance" in indexes:
                batch_op.drop_index("ix_suppliers_current_balance")
            
            for col_name in balance_columns:
                if col_name in columns:
                    batch_op.drop_column(col_name)
    else:
        indexes = {idx["name"] for idx in inspector.get_indexes("suppliers")}
        if "ix_suppliers_current_balance" in indexes:
            op.drop_index("ix_suppliers_current_balance", table_name="suppliers")
        
        for col_name in balance_columns:
            if col_name in columns:
                op.drop_column("suppliers", col_name)

